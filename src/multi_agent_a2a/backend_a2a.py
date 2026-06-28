"""FastAPI backend for the A2A multi-agent system (v2).

The exporter is fixed at startup via the EXPORTER_A2A environment variable.
All three processes (orchestrator, researcher, evaluator) read the same variable
so their traces are always sent to the same backend.

Run:
  uvicorn src.multi_agent_a2a.backend_a2a:app --reload --port 8002
"""

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from .config import MultiAgentA2AConfig
from .orchestrator import OrchestratorAgentA2A

load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("multi_agent_a2a.backend")

_STARTUP_EXPORTER: str = os.getenv("EXPORTER_A2A", "none")

EXPORTER_URLS: dict[str, str] = {
    "langfuse":    os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
    "phoenix":     os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006"),
    "opik":        os.getenv("OPIK_URL_OVERRIDE", "http://localhost:5173/api").removesuffix("/api"),
    "otel-stdout": "stdout",
    "none":        "—",
}

_agent: OrchestratorAgentA2A | None = None


def _get_agent() -> OrchestratorAgentA2A:
    global _agent
    if _agent is None:
        log.info("─" * 60)
        log.info(f"Initialising OrchestratorAgentA2A  exporter={_STARTUP_EXPORTER!r}")
        cfg = MultiAgentA2AConfig(exporter=_STARTUP_EXPORTER)
        _agent = OrchestratorAgentA2A(config=cfg)
        log.info(f"Researcher URL  : {cfg.researcher_url}")
        log.info(f"Evaluator URL   : {cfg.evaluator_url}")
        log.info(f"Exporter active : {_agent.tracing_active}")
        log.info("─" * 60)
    return _agent


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = _get_agent().config
    log.info("=" * 60)
    log.info("A2A Multi-Agent backend starting (port 8002)")
    log.info(f"Researcher service → {cfg.researcher_url}")
    log.info(f"Evaluator service  → {cfg.evaluator_url}")
    log.info(f"Exporter (EXPORTER_A2A) → {_STARTUP_EXPORTER}")
    log.info(f"Langfuse           → {EXPORTER_URLS['langfuse']}")
    log.info(f"Phoenix            → {EXPORTER_URLS['phoenix']}")
    log.info(f"Opik               → {EXPORTER_URLS['opik']}")
    log.info("=" * 60)
    _get_agent()  # initialise and instrument at startup
    yield
    log.info("A2A backend shutting down.")


app = FastAPI(title="Multi-Agent Research API (A2A v2)", lifespan=lifespan)


class ChatRequest(BaseModel):
    query: str
    session_id: str = ""


class ChatResponse(BaseModel):
    final_answer: str
    faithfulness: float
    label: str
    retry_count: int
    hitl_required: bool


@app.get("/health")
async def health() -> dict:
    """Liveness probe — returns the configured exporter."""
    return {"status": "ok", "service": "orchestrator", "exporter": _STARTUP_EXPORTER}


@app.delete("/session/{session_id}", status_code=204)
async def reset_session(session_id: str) -> None:
    _get_agent().reset_history(session_id)
    log.info(f"Conversation history reset for session={session_id}")


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    session_id = request.session_id or str(uuid.uuid4())
    log.info(f"[{_STARTUP_EXPORTER}] session={session_id} Query: {request.query[:120]!r}")
    t0 = time.perf_counter()
    state = await _get_agent().run_turn(request.query, session_id=session_id)
    elapsed = time.perf_counter() - t0
    evaluation = state["evaluation"]
    log.info(
        f"[{_STARTUP_EXPORTER}] session={session_id} Done in {elapsed:.2f}s — "
        f"faithfulness={evaluation.get('faithfulness', 0):.2f} hitl={state['hitl_required']}"
    )
    return ChatResponse(
        final_answer=state["final_answer"],
        faithfulness=evaluation.get("faithfulness", 0.0),
        label=evaluation.get("label", "unknown"),
        retry_count=state["retry_count"],
        hitl_required=state["hitl_required"],
    )
