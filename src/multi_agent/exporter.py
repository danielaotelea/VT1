"""Observability exporter adapters for the multi-agent system.

Strategy + Null Object pattern: build_exporter() always returns an ExporterAdapter
so callers never branch on None.  Adding a new backend means adding one subclass
and one entry in _BUILDERS — no changes needed in the orchestrator or any other consumer.
"""

import logging
import os
from contextlib import nullcontext
from typing import Any, Optional

from langfuse import propagate_attributes as langfuse_propagate_attributes
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler
from openinference.instrumentation.langchain import LangChainInstrumentor
from opentelemetry import trace as otel_trace
from opentelemetry.sdk.resources import Resource as OtelResource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, TraceIdRatioBased
from opik.integrations.langchain import OpikTracer
from phoenix.otel import Resource as PhoenixResource
from phoenix.otel import register as phoenix_register
from phoenix.otel import using_session

from src.otel_utils import otel_resource_attrs as _otel_resource_attrs

from .config import MultiAgentConfig

log = logging.getLogger("multi_agent.exporter")


# ---------------------------------------------------------------------------
# Adapter interface + Null Object
# ---------------------------------------------------------------------------

class ExporterAdapter:
    """Base adapter — no-op (tracing disabled). Subclasses override as needed."""

    active: bool = False
    exporter_name: str = "none"

    def _emit_log(self, agent_name: str, session_id: Optional[str] = None) -> None:
        """Log a DEBUG line when this adapter is about to emit a span/trace."""
        if not self.active:
            return
        from src.otel_utils import current_trace_id
        log.debug(
            f"[{agent_name}] emit → exporter={self.exporter_name} "
            f"trace_id={current_trace_id()} session={session_id or 'none'}"
        )

    def callback(self, session_id: Optional[str] = None, **_kwargs) -> Any:
        """Return a per-call LangChain callback handler, or None."""
        return None

    def session_ctx(self, session_id: Optional[str] = None):
        """Context manager that tags all spans in the block with session_id.

        Base is a no-op. _PhoenixAdapter overrides this to use
        openinference's using_session() so session.id propagates to child
        spans via OTel context without any per-call metadata plumbing.
        """
        return nullcontext()

    def trace_ctx(self, name: str):
        """Context manager that wraps a full agent run with a named trace.

        Base is a no-op. Override in adapters that require an outer trace scope.
        """
        return nullcontext()

    def tracked(self, fn, session_id: Optional[str] = None):
        """Wrap an async callable in an adapter-specific trace context.

        Base is a pass-through. _OpikAdapter overrides this to apply
        @opik.track so that opik_context.get_distributed_trace_headers()
        returns valid IDs during A2A network calls made inside *fn*.
        """
        return fn


# ---------------------------------------------------------------------------
# Concrete adapters
# ---------------------------------------------------------------------------

class _LangfuseAdapter(ExporterAdapter):
    active = True

    def __init__(self, client: Any):
        # Keep client reference for flush() capability.
        # LangfuseCallbackHandler uses the module-level singleton initialised here;
        # session context is propagated via session_ctx / langfuse_propagate_attributes.
        self._client = client

    def callback(self, session_id=None, **_kwargs):
        try:
            return LangfuseCallbackHandler()
        except Exception as exc:
            log.warning(f"LangfuseCallbackHandler init failed: {exc}")
            return None

    def session_ctx(self, session_id: Optional[str] = None):
        if not session_id:
            return nullcontext()
        return langfuse_propagate_attributes(session_id=session_id)


class _PhoenixAdapter(ExporterAdapter):
    """Phoenix auto-instruments via LangChainInstrumentor; no per-call callback needed."""
    active = True

    def session_ctx(self, session_id: Optional[str] = None):
        if not session_id:
            return nullcontext()
        return using_session(session_id=session_id)


class _OpikAdapter(ExporterAdapter):
    active = True

    def __init__(self, project: str):
        self._project = project

    def callback(self, session_id=None, **kwargs):
        try:
            return OpikTracer(
                project_name=self._project,
                thread_id=session_id or None,
                # Links this trace as a child when Opik distributed headers are present.
                # Only populated when the orchestrator had an active Opik span.
                distributed_headers=kwargs.get("distributed_headers") or None,
            )
        except Exception as exc:
            log.warning(f"OpikTracer init failed: {exc}")
            return None

    def tracked(self, fn, session_id: Optional[str] = None):
        """Wrap *fn* with @opik.track to create an Opik span context.

        Without this, opik_context.get_distributed_trace_headers() returns
        empty — Opik has no active span to read from when A2A network calls
        are made in LangGraph routing nodes (outside any OpikTracer LLM call).
        With this, sub-agent services receive valid opik_trace_id /
        opik_parent_span_id headers and create their traces as children.
        """
        import opik
        from opik import opik_context
        project = self._project
        _sid = session_id

        @opik.track(name="a2a_orchestrator_run", project_name=project,
                    capture_input=False, capture_output=False)
        async def _tracked(*args, **kwargs):
            if _sid:
                with suppress(Exception):
                    opik_context.update_current_trace(thread_id=_sid)
            return await fn(*args, **kwargs)

        return _tracked


class _OtelStdoutAdapter(ExporterAdapter):
    """OTel stdout — auto-instruments via LangChainInstrumentor; no per-call callback."""
    active = True


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def _uninstrument_langchain() -> None:
    """Remove the global LangChainInstrumentor patch if it is active.

    LangChainInstrumentor patches BaseCallbackManager.__init__ process-wide.
    When switching exporters (e.g. Phoenix → Opik), the old OTel-based
    instrumentation must be removed so spans no longer flow to the previous
    backend.
    """
    instrumentor = LangChainInstrumentor()
    if instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.uninstrument()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _build_langfuse(config: MultiAgentConfig) -> ExporterAdapter:
    from langfuse import Langfuse
    _uninstrument_langchain()
    host = os.getenv("LANGFUSE_HOST", "http://localhost:3000")
    client = Langfuse(
        public_key=config.langfuse_public_key or None,
        secret_key=config.langfuse_secret_key or None,
        host=host,
    )
    client.auth_check()  # raises if credentials are wrong — caught by build_exporter
    log.info(f"Exporter: langfuse initialised (url={host})")
    return _LangfuseAdapter(client=client)


def _build_phoenix(config: MultiAgentConfig) -> ExporterAdapter:
    _uninstrument_langchain()
    base = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
    project = config.phoenix_project_name
    os.environ["OTEL_TRACES_SAMPLER"] = "traceidratio"
    os.environ["OTEL_TRACES_SAMPLER_ARG"] = str(config.sampling_rate)
    tracer_provider = phoenix_register(
        project_name=project,
        endpoint=f"{base.rstrip('/')}/v1/traces",
        resource=PhoenixResource(_otel_resource_attrs(project)),
    )
    LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
    log.info(f"Exporter: phoenix initialised (project={project} endpoint={base} sampling={config.sampling_rate:.2f})")
    return _PhoenixAdapter()


def _build_opik(config: MultiAgentConfig) -> ExporterAdapter:
    _uninstrument_langchain()
    project = config.opik_project_name
    url = os.getenv("OPIK_URL_OVERRIDE", "http://localhost:5173/api")
    log.info(f"Exporter: opik initialised (project={project} url={url})")
    return _OpikAdapter(project=project)


def _build_otel_stdout(config: MultiAgentConfig) -> ExporterAdapter:
    _uninstrument_langchain()
    project = config.phoenix_project_name
    sampler = ALWAYS_ON if config.sampling_rate >= 1.0 else TraceIdRatioBased(config.sampling_rate)
    provider = TracerProvider(sampler=sampler, resource=OtelResource(_otel_resource_attrs(project)))
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    otel_trace.set_tracer_provider(provider)
    LangChainInstrumentor().instrument(tracer_provider=provider)
    log.info(f"Exporter: otel-stdout initialised (sampling={config.sampling_rate:.2f})")
    return _OtelStdoutAdapter()


_BUILDERS = {
    "langfuse":    _build_langfuse,
    "phoenix":     _build_phoenix,
    "opik":        _build_opik,
    "otel-stdout": _build_otel_stdout,
}


def build_exporter(config: MultiAgentConfig) -> ExporterAdapter:
    """Initialise the configured backend and return its adapter.

    Returns a no-op ExporterAdapter (active=False) when exporter="none"
    or when the backend fails to initialise, so callers never branch on None.
    """
    builder = _BUILDERS.get(config.exporter)
    if builder is None:
        log.info("Exporter: none (tracing disabled)")
        return ExporterAdapter()
    try:
        adapter = builder(config)
        adapter.exporter_name = config.exporter
        return adapter
    except Exception as exc:
        log.warning(f"Exporter {config.exporter!r} failed to initialise: {exc}", exc_info=True)
        return ExporterAdapter()
