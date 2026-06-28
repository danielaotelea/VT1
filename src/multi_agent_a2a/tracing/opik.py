"""Opik (Comet) distributed tracing strategy.

Opik uses its own header format instead of W3C traceparent:
  opik_trace_id        — links sub-agent spans to the orchestrator's Opik trace
  opik_parent_span_id  — establishes the parent-child span relationship

The core challenge: opik_context.get_distributed_trace_headers() only returns
valid values when an active Opik span exists in the current context.  In the
orchestrator's LangGraph routing nodes, Opik spans are created by OpikTracer
only during LLM calls — not during the A2A network dispatch steps that follow.
Without intervention, outgoing_headers() would always return empty and sub-agent
traces would appear as orphaned, independent traces in Opik.

Solution: wrap_run() applies @opik.track to the entire orchestrator run, creating
a root Opik span that stays active for the full request — including when
outgoing_headers() is called before each A2A call.

Span hierarchy in Opik UI (with wrap_run applied):
  a2a_orchestrator_run [opik.track]  ← root, created by wrap_run()
    researcher span                   ← sub-agent, linked via opik_trace_id header
    evaluator span                    ← sub-agent, linked via opik_trace_id header
    synthesis LLM span                ← orchestrator, from OpikTracer callback

Both _incoming_hdrs and _session_id ContextVars propagate into asyncio.to_thread()
worker threads automatically via Python's copy_context() mechanism.
"""

import logging
import os
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from typing import Any, Callable, Coroutine

from .base import SESSION_HEADER, TracingStrategy

log = logging.getLogger("multi_agent_a2a.tracing.opik")

# Per-request ContextVars — set by incoming_context(), read by get_callback().
_incoming_hdrs: ContextVar[dict] = ContextVar("opik_incoming_hdrs", default={})
_session_id: ContextVar[str | None] = ContextVar("opik_session_id", default=None)


class OpikTracingStrategy(TracingStrategy):
    name = "opik"
    active = True

    def setup(self, service_name: str) -> None:
        self._project = os.getenv("OPIK_PROJECT_NAME_A2A", "vt1-a2a")
        url = os.getenv("OPIK_URL_OVERRIDE", "http://localhost:5173/api")
        log.info(f"Opik: project={self._project!r} url={url!r} service={service_name!r}")

    def outgoing_headers(self, session_id: str | None = None) -> dict[str, str]:
        hdrs: dict[str, str] = {}

        try:
            from opik import opik_context
            opik_hdrs = opik_context.get_distributed_trace_headers()
            if opik_hdrs:
                hdrs.update(opik_hdrs)
            else:
                log.warning(
                    "Opik: get_distributed_trace_headers() returned empty — "
                    "no active Opik span (is wrap_run() missing on the orchestrator?)"
                )
        except Exception as exc:
            log.warning(f"Opik: failed to get distributed trace headers: {exc}")

        if session_id:
            hdrs[SESSION_HEADER] = session_id

        return hdrs

    @contextmanager
    def incoming_context(self, headers: dict):
        opik_hdrs: dict = {}
        if headers.get("opik_trace_id"):
            opik_hdrs = {
                "opik_trace_id":       headers["opik_trace_id"],
                "opik_parent_span_id": headers.get("opik_parent_span_id", ""),
            }
        else:
            log.debug("Opik incoming_context: no opik_trace_id in headers — standalone trace")

        incoming_session = headers.get(SESSION_HEADER)
        t1 = _incoming_hdrs.set(opik_hdrs)
        t2 = _session_id.set(incoming_session)
        try:
            yield
        finally:
            _incoming_hdrs.reset(t1)
            _session_id.reset(t2)

    def get_session_id(self) -> str | None:
        return _session_id.get()

    def get_callback(self, session_id: str | None = None) -> Any:
        try:
            from opik.integrations.langchain import OpikTracer
            distributed_headers = _incoming_hdrs.get() or None
            sid = session_id or _session_id.get()
            return OpikTracer(
                project_name=self._project,
                thread_id=sid or None,
                distributed_headers=distributed_headers,
            )
        except Exception as exc:
            log.warning(f"OpikTracer init failed: {exc}")
            return None

    def wrap_run(
        self,
        fn: Callable[..., Coroutine],
        session_id: str | None = None,
    ) -> Callable[..., Coroutine]:
        import opik
        from opik import opik_context

        project = self._project
        sid = session_id

        @opik.track(
            name="a2a_orchestrator_run",
            project_name=project,
            capture_input=False,
            capture_output=False,
        )
        async def _wrapped(*args, **kwargs):
            if sid:
                with suppress(Exception):
                    opik_context.update_current_trace(thread_id=sid)

            result = await fn(*args, **kwargs)

            # fn() returns an AgentState dict.  Populate the trace with:
            #   input/output  — messages format so the thread view shows the conversation
            #   metadata      — faithfulness, retry count, hitl flag for quick inspection
            #   span usage    — token counts aggregated across all three services
            with suppress(Exception):
                if not isinstance(result, dict):
                    return result

                query = result.get("query", "")
                answer = result.get("final_answer", "")
                evaluation = result.get("evaluation", {})

                opik_context.update_current_trace(
                    input={"messages": [{"role": "user", "content": query}]},
                    output={"messages": [{"role": "assistant", "content": answer}]},
                    metadata={
                        "faithfulness":  evaluation.get("faithfulness"),
                        "label":         evaluation.get("label"),
                        "retry_count":   result.get("retry_count", 0),
                        "hitl_required": result.get("hitl_required", False),
                    },
                )

                # Aggregate token usage from all trace events (researcher + evaluator
                # tokens travel back in the A2A response payload; synthesis tokens are
                # already tracked per-span by OpikTracer, but rolling them up here gives
                # a single total on the root trace).
                total_input = total_output = 0
                total_cost = 0.0
                for event in result.get("trace_events", []):
                    p = event.get("payload", {})
                    total_input  += p.get("input_tokens",  0)
                    total_output += p.get("output_tokens", 0)
                    total_cost   += p.get("cost_usd", 0.0)

                if total_input or total_output:
                    opik_context.update_current_span(
                        usage={
                            "prompt_tokens":     total_input,
                            "completion_tokens": total_output,
                            "total_tokens":      total_input + total_output,
                        },
                        total_cost=total_cost or None,
                    )

            return result

        return _wrapped
