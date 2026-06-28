"""Evaluator Agent — standalone A2A service.

Wraps FaithfulnessEvaluator as a JSON-RPC A2A service:

  Input  (data artifact): {"query": str, "research": ResearchResult}
  Output (data artifact): {"result": EvaluationResult, "trace_events": [...]}

Run:
  python -m src.multi_agent_a2a.evaluator_service
"""

import asyncio
import logging
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from a2a.helpers import get_data_parts, new_data_part, new_task_from_user_message, new_text_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import add_a2a_routes_to_fastapi, create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import TaskState

from src.multi_agent_a2a.evaluator import FaithfulnessEvaluator
from src.otel_utils import current_trace_id as _current_trace_id
from src.multi_agent_a2a.tracing import TracingStrategy, build_tracing
from .agent_cards import evaluator_card
from .config import MultiAgentA2AConfig
from .middleware import TracingMiddleware

log = logging.getLogger("multi_agent_a2a.evaluator_service")


class EvaluatorExecutor(AgentExecutor):
    """A2A executor bridging the A2A wire protocol to FaithfulnessEvaluator.run()."""

    def __init__(self, agent: FaithfulnessEvaluator, strategy: TracingStrategy | None = None) -> None:
        self._agent = agent
        self._strategy = strategy or TracingStrategy()

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task or new_task_from_user_message(context.message)
        if not context.current_task:
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue=event_queue, task_id=task.id, context_id=task.context_id)
        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message("Evaluating…"),
        )

        payload = get_data_parts(context.message.parts)[0]
        query: str = payload["query"]
        research = payload["research"]

        # Session ID and callback are read from the context set by TracingMiddleware.
        # incoming_context() has already run for this request; the strategy's ContextVars
        # (or W3C Baggage for Phoenix) are populated and propagate into asyncio.to_thread().
        session_id = self._strategy.get_session_id()
        callback = self._strategy.get_callback(session_id=session_id)
        log.info(f"[evaluator] trace_id={_current_trace_id()} session={session_id} query={query[:120]!r}")

        # FaithfulnessEvaluator.run() is synchronous (LangChain ChatOpenAI.invoke).
        # Run it in a thread so the event loop is not blocked during the LLM call.
        # The strategy's ContextVars (Langfuse trace ID, Opik headers, etc.) propagate
        # into the thread automatically via Python's copy_context() mechanism.
        with self._strategy.start_observation("evaluator_request"):
            result, events = await asyncio.to_thread(self._agent.run, query, research, callback)
            log.info(f"EvaluatorExecutor: faithfulness={result.get('faithfulness', 0):.2f} label={result.get('label')}")

            self._strategy.log_io(
                input={
                    "query": query,
                    "summary": research.get("summary", ""),
                },
                output={
                    "faithfulness": result.get("faithfulness", 0.0),
                    "label": result.get("label", ""),
                    "reason": result.get("raw_response", ""),
                },
            )

        await updater.add_artifact(
            parts=[new_data_part(data={"result": result, "trace_events": events})]
        )
        await updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message("Done."),
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("EvaluatorExecutor does not support cancellation.")


def build_app(agent: FaithfulnessEvaluator | None = None, port: int = 8012) -> FastAPI:
    """Build the FastAPI A2A app.  *agent* is injectable for tests."""
    url = f"http://127.0.0.1:{port}"
    card = evaluator_card(url)
    exporter = os.getenv("EXPORTER_A2A", "none")
    if exporter == "none":
        log.warning("EXPORTER_A2A is not set — evaluator service will run WITHOUT tracing.")

    strategy = build_tracing(exporter, service_name="evaluator")
    log.info(f"Evaluator service: exporter={exporter!r} active={strategy.active}")

    resolved_agent = agent or FaithfulnessEvaluator(config=MultiAgentA2AConfig(exporter=exporter))
    handler = DefaultRequestHandler(
        agent_executor=EvaluatorExecutor(resolved_agent, strategy),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = FastAPI(title="Evaluator Agent (A2A)")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "evaluator", "exporter": strategy.name}

    app.add_middleware(TracingMiddleware, strategy=strategy)
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, "/"),
    )
    return app


if __name__ == "__main__":
    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    _port = 8012
    log.info(f"Starting Evaluator Agent A2A service on port {_port}")
    uvicorn.run(build_app(port=_port), host="127.0.0.1", port=_port)
