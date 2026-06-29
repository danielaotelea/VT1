"""Phoenix (Arize) distributed tracing strategy.

Phoenix is pure OpenTelemetry, so this strategy delegates entirely to the OTel SDK:

  setup()            — registers a Phoenix OTLP exporter and instruments LangChain.
                       A custom sampler drops high-frequency A2A event-queue spans.
  outgoing_headers() — injects W3C traceparent + session.id via W3C Baggage.
  incoming_context() — extracts W3C context; tags the request with using_session().
  get_callback()     — returns None; LangChainInstrumentor creates spans automatically.
  wrap_run()         — creates an orchestrator_run root span.

Span hierarchy in Phoenix UI:
  orchestrator_run  [SERVER/AGENT]   ← from wrap_run()
    a2a.client…send_message           ← A2A outgoing call (kept)
      a2a.server…handle_requests      ← researcher/evaluator service (kept)
        ChatOpenAI                    ← auto-instrumented LLM call (kept)
    a2a.client…send_message           ← second A2A call for evaluation
      …
    ChatOpenAI                        ← synthesis LLM call (kept)

  (a2a.server.events.* spans are dropped by _DropA2ANoiseSampler — they are
   internal event-queue mechanics with 0ms duration and add no observability value)
"""

import logging
import os
from contextlib import contextmanager, nullcontext
from typing import Any, Callable, Coroutine

from .base import TracingStrategy

log = logging.getLogger("multi_agent_a2a.tracing.phoenix")

# Span name prefixes that carry no observability value and are safe to drop.
# Safe = they are leaf spans with no important children (LLM/tool calls).
#
# NOT dropped (ancestors of ChatOpenAI spans — dropping would orphan them):
#   a2a.server.routes.*        — JSON-RPC dispatcher; parent of request_handlers
#   a2a.client.transports.*    — HTTP transport; parent of server-side spans
#   a2a.server.request_handlers.* — direct parent of ChatOpenAI spans
#
# To remove those without orphaning children a SpanProcessor that rewrites
# parent_span_id would be needed (not implemented).
_A2A_NOISE_PREFIXES = (
    "a2a.server.events.",  # EventQueueSource internals: dozens of 0ms spans per request
    "a2a.server.tasks.",   # TaskManager internals: leaf spans, no LLM children
)


class _DropA2ANoiseSampler:
    """OTel-compatible sampler that drops A2A event-queue spans."""

    def should_sample(self, parent_context, trace_id, name, kind=None, attributes=None, links=None, trace_state=None):
        from opentelemetry.sdk.trace.sampling import Decision, SamplingResult, ALWAYS_ON
        if any(name.startswith(p) for p in _A2A_NOISE_PREFIXES):
            return SamplingResult(Decision.DROP, attributes=None, trace_state=trace_state)
        return ALWAYS_ON.should_sample(parent_context, trace_id, name, kind, attributes, links, trace_state)

    def get_description(self) -> str:
        return "DropA2ANoiseSampler"


class PhoenixTracingStrategy(TracingStrategy):
    name = "phoenix"
    active = True

    def setup(self, service_name: str) -> None:
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from phoenix.otel import Resource as PhoenixResource
        from phoenix.otel import register as phoenix_register
        from src.otel_utils import otel_resource_attrs

        base = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
        project = os.getenv("PHOENIX_PROJECT_NAME_A2A", "vt1-a2a")

        inst = LangChainInstrumentor()
        if inst.is_instrumented_by_opentelemetry:
            inst.uninstrument()

        tracer_provider = phoenix_register(
            project_name=project,
            endpoint=f"{base.rstrip('/')}/v1/traces",
            resource=PhoenixResource(otel_resource_attrs(service_name)),
            sampler=_DropA2ANoiseSampler(),
        )
        LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
        log.info(f"Phoenix: project={project!r} endpoint={base} service={service_name!r} noise_filter=on")

    def outgoing_headers(self, session_id: str | None = None) -> dict[str, str]:
        from opentelemetry import context as otel_ctx
        from opentelemetry.baggage import set_baggage
        from opentelemetry.propagate import inject

        ctx = otel_ctx.get_current()
        if session_id:
            ctx = set_baggage("session.id", session_id, context=ctx)

        carrier: dict[str, str] = {}
        inject(carrier, context=ctx)

        if not carrier:
            log.warning(
                "Phoenix: outgoing_headers produced no traceparent — "
                "no active recording span (is wrap_run() missing on the orchestrator?)"
            )
        return carrier

    @contextmanager
    def incoming_context(self, headers: dict):
        from opentelemetry import context as otel_ctx
        from opentelemetry.baggage import get_baggage
        from opentelemetry.propagate import extract
        from phoenix.otel import using_session

        ctx = extract(headers)
        token = otel_ctx.attach(ctx)
        try:
            session_id = get_baggage("session.id", context=ctx)
            with (using_session(str(session_id)) if session_id else nullcontext()):
                yield
        finally:
            otel_ctx.detach(token)

    def get_session_id(self) -> str | None:
        from opentelemetry.baggage import get_baggage
        return get_baggage("session.id") or None

    def get_callback(self, session_id: str | None = None) -> None:
        return None  # auto-instrumented via LangChainInstrumentor

    def wrap_run(
        self,
        fn: Callable[..., Coroutine],
        session_id: str | None = None,
    ) -> Callable[..., Coroutine]:
        from opentelemetry import trace as otel_trace
        from opentelemetry.trace import SpanKind, StatusCode
        from phoenix.otel import using_session

        tracer = otel_trace.get_tracer("multi_agent_a2a.orchestrator")

        async def _wrapped(*args, **kwargs):
            with (using_session(session_id) if session_id else nullcontext()):
                with tracer.start_as_current_span(
                    "orchestrator_run", kind=SpanKind.SERVER
                ) as span:
                    span.set_attribute("openinference.span.kind", "AGENT")
                    try:
                        result = await fn(*args, **kwargs)
                        # Phoenix session view reads input.value / output.value from the
                        # root span of each trace to populate the HUMAN / AI turn display.
                        if isinstance(result, dict):
                            span.set_attribute("input.value",    result.get("query", ""))
                            span.set_attribute("output.value",   result.get("final_answer", ""))
                            span.set_attribute("input.mime_type", "text/plain")
                            span.set_attribute("output.mime_type", "text/plain")
                        span.set_status(StatusCode.OK)
                        return result
                    except Exception as exc:
                        from src.otel_utils import record_exception
                        record_exception(exc)
                        raise

        return _wrapped
