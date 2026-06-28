"""OTel stdout tracing strategy — prints spans to the console.

Useful for local development without a running observability backend.  Span
hierarchy and W3C context propagation work identically to Phoenix; the only
difference is the exporter (console instead of OTLP).

Spans are printed as JSON to stdout.  Each service prints its own spans; the
shared trace ID in the headers ties them together in the log output.
"""

import logging
import os
from contextlib import contextmanager
from typing import Callable, Coroutine

from opentelemetry import context as otel_ctx
from opentelemetry import trace as otel_trace
from opentelemetry.baggage import get_baggage, set_baggage
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.resources import Resource as OtelResource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, TraceIdRatioBased
from opentelemetry.trace import SpanKind

from .base import TracingStrategy

log = logging.getLogger("multi_agent_a2a.tracing.otel_stdout")


class OtelStdoutTracingStrategy(TracingStrategy):
    name = "otel-stdout"
    active = True

    def setup(self, service_name: str) -> None:
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from src.otel_utils import otel_resource_attrs

        sampling_rate = float(os.getenv("OTEL_TRACES_SAMPLER_ARG", "1.0"))
        sampler = ALWAYS_ON if sampling_rate >= 1.0 else TraceIdRatioBased(sampling_rate)

        provider = TracerProvider(
            sampler=sampler,
            resource=OtelResource(otel_resource_attrs(service_name)),
        )
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
        otel_trace.set_tracer_provider(provider)

        inst = LangChainInstrumentor()
        if inst.is_instrumented_by_opentelemetry:
            inst.uninstrument()
        LangChainInstrumentor().instrument(tracer_provider=provider)
        log.info(f"OTel-stdout: service={service_name!r} sampling={sampling_rate}")

    def outgoing_headers(self, session_id: str | None = None) -> dict[str, str]:
        ctx = otel_ctx.get_current()
        if session_id:
            ctx = set_baggage("session.id", session_id, context=ctx)
        carrier: dict[str, str] = {}
        inject(carrier, context=ctx)
        if not carrier:
            log.warning(
                "OTel-stdout: outgoing_headers produced no traceparent — "
                "no active recording span (is wrap_run() missing?)"
            )
        return carrier

    @contextmanager
    def incoming_context(self, headers: dict):
        ctx = extract(headers)
        token = otel_ctx.attach(ctx)
        try:
            yield
        finally:
            otel_ctx.detach(token)

    def get_session_id(self) -> str | None:
        from opentelemetry.baggage import get_baggage
        return get_baggage("session.id") or None

    def get_callback(self, session_id: str | None = None):
        return None  # auto-instrumented via LangChainInstrumentor

    def wrap_run(
        self,
        fn: Callable[..., Coroutine],
        session_id: str | None = None,
    ) -> Callable[..., Coroutine]:
        tracer = otel_trace.get_tracer("multi_agent_a2a.orchestrator")

        async def _wrapped(*args, **kwargs):
            with tracer.start_as_current_span("orchestrator_run", kind=SpanKind.SERVER):
                return await fn(*args, **kwargs)

        return _wrapped
