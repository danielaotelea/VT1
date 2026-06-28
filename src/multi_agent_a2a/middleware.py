"""ASGI middleware for A2A sub-agent services.

TracingMiddleware delegates every incoming request to the active strategy's
incoming_context() — a single context manager that handles everything the
tool needs: span context extraction, session tagging, ContextVar population.

Each tool's logic lives entirely in its own tracing strategy file:
  Phoenix   → tracing/phoenix.py   (W3C extract + using_session)
  Langfuse  → tracing/langfuse.py  (x-langfuse-trace-id ContextVar)
  Opik      → tracing/opik.py      (opik_trace_id ContextVar)
  otel-stdout → tracing/otel_stdout.py (W3C extract only)
  none      → tracing/base.py      (no-op)
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.multi_agent_a2a.tracing import TracingStrategy


class TracingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, strategy: TracingStrategy) -> None:
        super().__init__(app)
        self._strategy = strategy

    async def dispatch(self, request: Request, call_next):
        with self._strategy.incoming_context(dict(request.headers)):
            return await call_next(request)
