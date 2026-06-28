"""Langfuse distributed tracing strategy (Langfuse v4 / OTel-native API).

Langfuse v4 is fully OTel-based.  Key API differences from v2/v3:

  OLD (v2):  lf.trace(name=..., session_id=...)  →  trace object with .id
             CallbackHandler(public_key=..., secret_key=..., host=..., trace_id=...)
  NEW (v4):  lf.start_as_current_observation(name=..., as_type="agent")  →  span ctxmgr
             lf.get_current_trace_id()             →  reads from OTel context
             propagate_attributes(session_id=...)  →  stamps session on all child spans
             CallbackHandler(trace_context=TraceContext(trace_id=...))

Distributed tracing flow:

  Orchestrator
    wrap_run() enters propagate_attributes(session_id=...) then
    start_as_current_observation().  The trace ID is read via
    get_current_trace_id() and stored in _trace_id ContextVar so that
    outgoing_headers() can inject it as x-langfuse-trace-id into every A2A call.

  Sub-agents (researcher / evaluator)
    incoming_context() extracts x-langfuse-trace-id and x-a2a-session-id, stores
    them in ContextVars, AND enters propagate_attributes(session_id=...) so that
    all LangChain spans created during the request inherit the session attribute.
    get_callback() passes the trace ID to CallbackHandler(trace_context=...) so
    all observations land under the same Langfuse trace.

Both ContextVars propagate into asyncio.to_thread() worker threads automatically
via Python's copy_context() mechanism — OTel context follows the same path.
"""

import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Coroutine

from .base import SESSION_HEADER, TracingStrategy

log = logging.getLogger("multi_agent_a2a.tracing.langfuse")

TRACE_ID_HEADER = "x-langfuse-trace-id"

# Span name prefixes to suppress before they reach Langfuse.
# a2a.server.events.* = EventQueueSource internals (_dispatch_loop, enqueue_event, …)
# These are high-frequency, zero-duration spans with no observability value.
_A2A_NOISE_PREFIXES = ("a2a.server.events.",)

# Per-request ContextVars — set by incoming_context(), read by get_callback() / log_io().
_trace_id: ContextVar[str | None] = ContextVar("langfuse_trace_id", default=None)
_session_id: ContextVar[str | None] = ContextVar("langfuse_session_id", default=None)
# Holds the Langfuse-managed root observation opened in incoming_context() so that
# log_io() can call .update() directly instead of relying on update_current_observation(),
# which only works when a Langfuse-managed span (not an A2A SDK OTel span) is current.
_root_obs: ContextVar[Any] = ContextVar("langfuse_root_obs", default=None)


class LangfuseTracingStrategy(TracingStrategy):
    name = "langfuse"
    active = True

    def __init__(self) -> None:
        self._lf = None
        self._service_name = "unknown"

    def setup(self, service_name: str) -> None:
        # Fix 1: stamp the OTel resource with the concrete service name before Langfuse
        # initialises its own TracerProvider.  Without this every service reports
        # service.name = "unknown_service", making traces indistinguishable.
        os.environ.setdefault("OTEL_SERVICE_NAME", service_name)
        self._service_name = service_name

        from langfuse import Langfuse

        public_key = os.getenv("LANGFUSE_PUBLIC_KEY_A2A") or os.getenv("LANGFUSE_PUBLIC_KEY")
        secret_key = os.getenv("LANGFUSE_SECRET_KEY_A2A") or os.getenv("LANGFUSE_SECRET_KEY")
        host = os.getenv("LANGFUSE_HOST", "http://localhost:3000")

        # Langfuse() validates credentials at startup — raises early rather than
        # silently dropping spans.
        # should_export_span filters out A2A event-queue noise spans before export.
        self._lf = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
            should_export_span=lambda span: not any(
                span.name.startswith(p) for p in _A2A_NOISE_PREFIXES
            ),
        )
        log.info(f"Langfuse v4: host={host!r} service={service_name!r} noise_filter=on")

    def outgoing_headers(self, session_id: str | None = None) -> dict[str, str]:
        hdrs: dict[str, str] = {}

        trace_id = _trace_id.get()
        if trace_id:
            hdrs[TRACE_ID_HEADER] = trace_id
        else:
            log.warning(
                "Langfuse: no active trace ID — sub-agent observations will not be "
                "linked to the orchestrator trace (is wrap_run() missing?)"
            )

        if session_id:
            hdrs[SESSION_HEADER] = session_id

        return hdrs

    @contextmanager
    def incoming_context(self, headers: dict):
        from langfuse import propagate_attributes

        incoming_trace_id = headers.get(TRACE_ID_HEADER)
        incoming_session = headers.get(SESSION_HEADER)
        if not incoming_trace_id:
            log.debug("Langfuse incoming_context: no trace ID in headers — standalone observation")

        t1 = _trace_id.set(incoming_trace_id)
        t2 = _session_id.set(incoming_session)
        try:
            # propagate_attributes stamps session_id on every OTel span created in
            # this context, including spans created inside asyncio.to_thread() workers
            # (OTel context propagates via copy_context()).  Without this, sub-agent
            # observations inherit the trace ID but not the session grouping.
            with propagate_attributes(
                session_id=incoming_session or None,
                tags=[f"session:{incoming_session}"] if incoming_session else None,
            ):
                yield
        finally:
            _trace_id.reset(t1)
            _session_id.reset(t2)

    def get_session_id(self) -> str | None:
        return _session_id.get()

    @contextmanager
    def start_observation(self, name: str):
        """Open a Langfuse child span inside the executor's A2A OTel context.

        Called from within execute(), so the A2A SDK's root span (handle_requests)
        is already active — our span becomes a child, not a new trace root.
        This eliminates the phantom duplicate trace that appeared when
        start_as_current_observation() was called from the ASGI middleware layer.
        """
        if self._lf is None:
            yield
            return
        with self._lf.start_as_current_observation(name=name, as_type="span") as obs:
            token = _root_obs.set(obs)
            try:
                yield
            finally:
                _root_obs.reset(token)

    def get_callback(self, session_id: str | None = None) -> Any:
        from langfuse.langchain import CallbackHandler
        from langfuse.types import TraceContext

        trace_id = _trace_id.get()
        if trace_id:
            # Link this LangChain execution to the orchestrator's root trace so
            # all observations appear nested under the same Langfuse trace.
            return CallbackHandler(trace_context=TraceContext(trace_id=trace_id))
        return CallbackHandler()

    def log_io(self, input: dict, output: dict) -> None:
        """Stamp the root service observation with semantic input / output.

        Prefers the Langfuse-managed span stored in _root_obs by start_observation()
        over update_current_observation(), because the latter only works when a
        Langfuse-managed span is current — inside A2A request handling, the current
        OTel span is always an a2a-python-sdk span, so the context lookup fails.
        """
        if self._lf is None:
            return
        root = _root_obs.get()
        if root is not None:
            try:
                root.update(input=input, output=output)
                return
            except Exception as exc:
                log.warning(f"Langfuse: log_io root.update() failed: {exc}")
        try:
            self._lf.update_current_observation(input=input, output=output)
        except Exception as exc:
            log.warning(f"Langfuse: log_io failed: {exc}")

    def wrap_run(
        self,
        fn: Callable[..., Coroutine],
        session_id: str | None = None,
    ) -> Callable[..., Coroutine]:
        if self._lf is None:
            log.warning("Langfuse: setup() was not called — returning fn unwrapped")
            return fn

        lf = self._lf

        async def _wrapped(*args, **kwargs):
            from langfuse import propagate_attributes

            # propagate_attributes must be the outermost context so the session_id
            # attribute is inherited by the root observation itself and all children.
            # A tag is also added so traces are filterable by session in the UI.
            try:
                with propagate_attributes(
                    session_id=session_id or None,
                    tags=[f"session:{session_id}"] if session_id else None,
                ):
                    with lf.start_as_current_observation(
                        name="a2a_orchestrator_run",
                        as_type="agent",
                    ) as span:
                        trace_id = lf.get_current_trace_id()
                        token = _trace_id.set(trace_id)
                        log.debug(f"Langfuse root trace: id={trace_id!r} session={session_id!r}")
                        try:
                            result = await fn(*args, **kwargs)
                        finally:
                            _trace_id.reset(token)

                        # Populate the observation once the run has completed.
                        # span.update() sets input/output/metadata/usage on the
                        # observation itself (visible in observation detail view).
                        # set_trace_io() is intentionally NOT used — it is deprecated
                        # in v4; setting input/output on the root observation is the
                        # recommended way and also populates the trace-level display.
                        if isinstance(result, dict):
                            query      = result.get("query", "")
                            answer     = result.get("final_answer", "")
                            evaluation = result.get("evaluation", {})

                            # Aggregate token usage across all three services.
                            # Researcher / evaluator tokens travel back in the A2A
                            # response payload via trace_events; synthesis tokens are
                            # tracked by OpikTracer per-span but also land in events.
                            total_input = total_output = 0
                            total_cost  = 0.0
                            for event in result.get("trace_events", []):
                                p = event.get("payload", {})
                                total_input  += p.get("input_tokens",  0)
                                total_output += p.get("output_tokens", 0)
                                total_cost   += p.get("cost_usd",      0.0)

                            span.update(
                                input  = {"messages": [{"role": "user",      "content": query}]},
                                output = {"messages": [{"role": "assistant", "content": answer}]},
                                metadata = {
                                    "faithfulness":  evaluation.get("faithfulness"),
                                    "label":         evaluation.get("label"),
                                    "retry_count":   result.get("retry_count",   0),
                                    "hitl_required": result.get("hitl_required", False),
                                },
                                usage_details = (
                                    {"input": total_input, "output": total_output,
                                     "total": total_input + total_output}
                                    if total_input or total_output else None
                                ),
                                cost_details = (
                                    {"total": total_cost}
                                    if total_cost else None
                                ),
                            )

                        return result
            finally:
                lf.flush()

        return _wrapped
