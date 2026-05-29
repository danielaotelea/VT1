"""Observability exporter adapters for the multi-agent system.

Each adapter encapsulates one backend's SDK initialisation and per-call
callback creation behind a single interface.  The factory build_exporter()
returns a NullAdapter when tracing is disabled, so callers never branch on None.

Adding a new backend means adding one class and one entry in _BUILDERS — no
changes to the orchestrator or any other consumer.
"""

import logging
import os
from contextlib import suppress
from typing import Any, Optional

from .config import MultiAgentConfig
from src.otel_utils import otel_resource_attrs as _otel_resource_attrs

log = logging.getLogger("multi_agent.exporter")


# ---------------------------------------------------------------------------
# Adapter interface + Null Object
# ---------------------------------------------------------------------------

class ExporterAdapter:
    """Base adapter: no-op (tracing disabled).  Subclasses override callback()."""

    active: bool = False

    def callback(self, session_id: Optional[str] = None) -> Any:
        """Return a per-call LangChain callback handler, or None."""
        return None

    def session_ctx(self, session_id: Optional[str] = None):
        """Return a context manager that tags all spans with session_id.

        Base implementation is a no-op.  _PhoenixAdapter overrides this to use
        openinference's using_session() so every child span inherits session.id
        via OTel context propagation without any per-call metadata plumbing.
        """
        from contextlib import nullcontext
        return nullcontext()


# ---------------------------------------------------------------------------
# Concrete adapters
# ---------------------------------------------------------------------------

class _LangwatchAdapter(ExporterAdapter):
    active = True

    def __init__(self, lw):
        self._lw = lw

    def callback(self, session_id=None):
        with suppress(Exception):
            return self._lw.get_current_trace().get_langchain_callback()
        return None


class _LangfuseAdapter(ExporterAdapter):
    active = True

    def callback(self, session_id=None):
        with suppress(Exception):
            from langfuse.langchain import CallbackHandler
            ctx = {"session_id": session_id} if session_id else None
            return CallbackHandler(trace_context=ctx)
        return None


class _PhoenixAdapter(ExporterAdapter):
    """Phoenix auto-instruments via LangChainInstrumentor; no per-call handler."""
    active = True

    def session_ctx(self, session_id: Optional[str] = None):
        if not session_id:
            from contextlib import nullcontext
            return nullcontext()
        from openinference.instrumentation import using_session
        return using_session(session_id=session_id)


class _OpikAdapter(ExporterAdapter):
    active = True

    def __init__(self, project: str):
        self._project = project

    def callback(self, session_id=None):
        with suppress(Exception):
            from opik.integrations.langchain import OpikTracer
            meta = {"session_id": session_id} if session_id else {}
            return OpikTracer(project_name=self._project, metadata=meta)
        return None


class _OtelStdoutAdapter(ExporterAdapter):
    """OTel stdout auto-instruments via LangChainInstrumentor; no per-call handler."""
    active = True


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _build_langwatch(config: MultiAgentConfig) -> ExporterAdapter:
    import langwatch
    langwatch.setup()
    log.info("Exporter: langwatch initialised")
    return _LangwatchAdapter(langwatch)


def _build_langfuse(config: MultiAgentConfig) -> ExporterAdapter:
    from langfuse.langchain import CallbackHandler
    CallbackHandler()  # validates credentials at startup
    log.info("Exporter: langfuse initialised (url=%s)", os.getenv("LANGFUSE_HOST", "http://localhost:3000"))
    return _LangfuseAdapter()


def _build_phoenix(config: MultiAgentConfig) -> ExporterAdapter:
    from phoenix.otel import register
    from openinference.instrumentation.langchain import LangChainInstrumentor
    base = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
    project = os.getenv("PHOENIX_PROJECT_NAME", "vt1-multi-agent")
    os.environ.setdefault("OTEL_TRACES_SAMPLER", "traceidratio")
    os.environ.setdefault("OTEL_TRACES_SAMPLER_ARG", str(config.sampling_rate))
    tracer_provider = register(
        project_name=project,
        endpoint=f"{base.rstrip('/')}/v1/traces",
    )
    instrumentor = LangChainInstrumentor()
    if not instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.instrument(tracer_provider=tracer_provider)
    log.info("Exporter: phoenix initialised (project=%s endpoint=%s sampling=%.2f)",
             project, base, config.sampling_rate)
    return _PhoenixAdapter()


def _build_opik(config: MultiAgentConfig) -> ExporterAdapter:
    from opik.integrations.langchain import OpikTracer
    project = os.getenv("OPIK_PROJECT_NAME", "vt1-multi-agent")
    log.info("Exporter: opik initialised (project=%s url=%s)", project,
             os.getenv("OPIK_URL_OVERRIDE", "http://localhost:5173/api"))
    return _OpikAdapter(project=project)


def _build_otel_stdout(config: MultiAgentConfig) -> ExporterAdapter:
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
    from opentelemetry.sdk.trace.sampling import ALWAYS_ON, TraceIdRatioBased
    from openinference.instrumentation.langchain import LangChainInstrumentor
    project = os.getenv("PHOENIX_PROJECT_NAME", "vt1-multi-agent")
    sampler = ALWAYS_ON if config.sampling_rate >= 1.0 else TraceIdRatioBased(config.sampling_rate)
    provider = TracerProvider(sampler=sampler, resource=Resource(_otel_resource_attrs(project)))
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    otel_trace.set_tracer_provider(provider)
    LangChainInstrumentor().instrument(tracer_provider=provider)
    log.info("Exporter: otel-stdout initialised (sampling=%.2f)", config.sampling_rate)
    return _OtelStdoutAdapter()


_BUILDERS = {
    "langwatch":   _build_langwatch,
    "langfuse":    _build_langfuse,
    "phoenix":     _build_phoenix,
    "opik":        _build_opik,
    "otel-stdout": _build_otel_stdout,
}


def build_exporter(config: MultiAgentConfig) -> ExporterAdapter:
    """Initialise the configured backend and return its adapter.

    Returns a no-op ExporterAdapter (active=False) when exporter="none"
    or when the backend fails to initialise, so callers never need to
    branch on None.
    """
    builder = _BUILDERS.get(config.exporter)
    if builder is None:
        log.info("Exporter: none (tracing disabled)")
        return ExporterAdapter()
    try:
        return builder(config)
    except Exception as exc:
        log.warning("Exporter %r failed to initialise: %s", config.exporter, exc, exc_info=True)
        return ExporterAdapter()
