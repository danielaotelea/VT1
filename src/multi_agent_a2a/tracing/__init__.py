"""Distributed tracing strategies for the A2A multi-agent system.

build_tracing(name, service_name) instantiates, initialises, and returns the
TracingStrategy for the requested backend.  It always returns a valid strategy:
  - unknown or "none" names → no-op TracingStrategy (active=False)
  - initialisation errors   → no-op TracingStrategy with a logged warning

Usage (one call per service process at startup):

    from src.multi_agent_a2a.tracing import build_tracing

    strategy = build_tracing("phoenix", service_name="researcher")
    # strategy is now ready to use:
    strategy.outgoing_headers(session_id)   # orchestrator side
    strategy.incoming_context(headers)      # sub-agent middleware
    strategy.get_callback(session_id)       # sub-agent executor
    strategy.wrap_run(fn, session_id)       # orchestrator side
"""

import logging

from .base import TracingStrategy
from .langfuse import LangfuseTracingStrategy
from .opik import OpikTracingStrategy
from .otel_stdout import OtelStdoutTracingStrategy
from .phoenix import PhoenixTracingStrategy

log = logging.getLogger("multi_agent_a2a.tracing")

_STRATEGIES: dict[str, type[TracingStrategy]] = {
    "phoenix":     PhoenixTracingStrategy,
    "langfuse":    LangfuseTracingStrategy,
    "opik":        OpikTracingStrategy,
    "otel-stdout": OtelStdoutTracingStrategy,
}

__all__ = [
    "TracingStrategy",
    "PhoenixTracingStrategy",
    "LangfuseTracingStrategy",
    "OpikTracingStrategy",
    "OtelStdoutTracingStrategy",
    "build_tracing",
]


def build_tracing(name: str, service_name: str = "a2a") -> TracingStrategy:
    """Return an initialised TracingStrategy for *name*.

    Parameters
    ----------
    name:
        One of "phoenix", "langfuse", "opik", "otel-stdout", or "none".
    service_name:
        Identifies this process in the observability backend (e.g. "orchestrator",
        "researcher", "evaluator").  Used as the OTel service.name resource attribute
        and in log messages.
    """
    cls = _STRATEGIES.get(name)
    if cls is None:
        if name not in ("none", ""):
            log.warning(f"Unknown tracing backend {name!r} — tracing disabled")
        return TracingStrategy()

    strategy = cls()
    try:
        strategy.setup(service_name=service_name)
        return strategy
    except Exception as exc:
        log.warning(
            f"Tracing backend {name!r} failed to initialise: {exc} — tracing disabled",
            exc_info=True,
        )
        return TracingStrategy()
