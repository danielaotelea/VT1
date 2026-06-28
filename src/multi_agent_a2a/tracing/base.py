"""Abstract base for per-tool distributed-tracing strategies.

Each concrete strategy owns the complete distributed-tracing lifecycle for one
observability tool across all three services (orchestrator, researcher, evaluator):

  setup()            — one-time SDK initialisation + LangChain instrumentation.
                       Called once at service startup.

  outgoing_headers() — HTTP headers the orchestrator injects before each A2A call.
                       Must be called while an active root span exists (see wrap_run).

  incoming_context() — context manager that restores trace context from the
                       incoming HTTP request headers.  Used in sub-agent middleware.

  get_callback()     — per-request LangChain callback, or None when spans are
                       created automatically by LangChainInstrumentor.

  wrap_run()         — wraps the orchestrator's async run function with a root
                       trace / span.  Required so outgoing_headers() has an active
                       span to inject when the A2A calls are made.

All methods have safe no-op defaults so callers never branch on None.
"""

from contextlib import contextmanager
from typing import Any, Callable, Coroutine

# All strategies include this header in outgoing_headers() so sub-agents can
# read the session_id without depending on W3C Baggage or tool-specific headers.
SESSION_HEADER = "x-a2a-session-id"


class TracingStrategy:
    """Base (no-op) strategy — returned when tracing is disabled or setup fails."""

    name: str = "none"
    active: bool = False

    def setup(self, service_name: str) -> None:
        """Initialise the observability SDK.  Called once per service process."""

    def outgoing_headers(self, session_id: str | None = None) -> dict[str, str]:
        """Return HTTP headers to inject before each outgoing A2A call."""
        return {}

    @contextmanager
    def incoming_context(self, headers: dict):
        """Restore distributed trace context from incoming request headers."""
        yield

    def get_session_id(self) -> str | None:
        """Return the session ID restored by the most recent incoming_context() call.

        Must be called from within an incoming_context() block.
        Base always returns None; concrete strategies override to read from their
        specific context store (W3C Baggage or a ContextVar).
        """
        return None

    def get_callback(self, session_id: str | None = None) -> Any:
        """Per-request LangChain callback, or None when auto-instrumented."""
        return None

    def wrap_run(
        self,
        fn: Callable[..., Coroutine],
        session_id: str | None = None,
    ) -> Callable[..., Coroutine]:
        """Wrap the orchestrator's async run with a root trace span if needed.

        The base is a pass-through.  Concrete strategies override this to create
        the root span/trace that outgoing_headers() will inject into A2A calls.
        """
        return fn

    @contextmanager
    def start_observation(self, name: str):
        """Context manager that opens a named observation around the agent run.

        Called from sub-agent executors (researcher, evaluator) so that the
        observation is created *inside* the A2A SDK's active span rather than
        from the ASGI middleware layer.  Creating it inside means it becomes a
        genuine child of the A2A root span instead of a new trace root, which
        prevents phantom duplicate traces.

        log_io() should be called from within this context so it can target the
        observation directly.  The base is a no-op pass-through.
        """
        yield

    def log_io(self, input: dict, output: dict) -> None:
        """Stamp the current observation / span with semantic input and output.

        Called from sub-agent executors (researcher, evaluator) after each run
        so that Langfuse (and other backends) display the query / result instead
        of raw A2A protocol data.

        The base is a no-op.  Concrete strategies override when their SDK
        provides a way to update the active observation (e.g. Langfuse v4's
        update_current_observation, or Opik's opik_context.update_current_span).
        """
