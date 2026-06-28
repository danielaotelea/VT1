"""FastAPI backend for the multi-agent Research & Fact-Check system."""

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from .config import ExporterName, MultiAgentConfig
from .orchestrator import OrchestratorAgent

load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("multi_agent.backend")

_agents: dict[str, OrchestratorAgent] = {}

EXPORTER_URLS: dict[str, str] = {
    "langfuse": os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
    "phoenix": os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006"),
    "opik": os.getenv("OPIK_URL_OVERRIDE", "http://localhost:5173/api").removesuffix("/api"),
    "otel-stdout": "stdout",
    "none": "—",
}

_NETWORK_EXPORTERS = {"langfuse", "phoenix", "opik"}


def _check_endpoint(url: str) -> tuple[bool, str]:
    try:
        httpx.get(url, timeout=3)
        return True, url
    except Exception as e:
        return False, f"unreachable — {e}"


def get_agent(exporter: ExporterName) -> OrchestratorAgent:
    if exporter not in _agents:
        log.info("─" * 60)
        log.info(f"Initialising OrchestratorAgent  exporter={exporter!r}")
        log.info(f"Collector URL                  : {EXPORTER_URLS.get(exporter, 'unknown')}")
        agent = OrchestratorAgent(config=MultiAgentConfig(exporter=exporter))
        log.info(f"Exporter active                : {agent.tracing_active}")
        log.info("─" * 60)
        _agents[exporter] = agent
    return _agents[exporter]


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=" * 60)
    log.info("Multi-Agent backend starting")
    log.info(f"Langfuse  → {EXPORTER_URLS['langfuse']}")
    log.info(f"Phoenix   → {EXPORTER_URLS['phoenix']}")
    log.info(f"Opik      → {EXPORTER_URLS['opik']}")
    log.info("Default exporter: none")
    log.info("=" * 60)
    yield
    log.info(f"Multi-Agent backend shutting down. Active exporters: {list(_agents.keys())}")


app = FastAPI(title="Multi-Agent Research API", lifespan=lifespan)


class ChatRequest(BaseModel):
    query: str
    exporter: ExporterName = "none"
    session_id: str = ""


class ChatResponse(BaseModel):
    final_answer: str
    faithfulness: float
    hitl_required: bool


class ExporterStatus(BaseModel):
    exporter: str
    active: bool
    collector_url: str


@app.get("/health")
def health() -> dict:
    """Liveness probe — returns active exporters."""
    return {"status": "ok", "active_exporters": list(_agents.keys())}


@app.delete("/session/{session_id}", status_code=204)
def reset_session(session_id: str) -> None:
    """Discard the conversation history for *session_id* on all active agents."""
    for agent in _agents.values():
        agent.reset_history(session_id)
    log.info(f"Conversation history reset for session={session_id}")


@app.post("/exporter/{name}", response_model=ExporterStatus)
def activate_exporter(name: ExporterName) -> ExporterStatus:
    url = EXPORTER_URLS.get(name, "—")
    if name in _NETWORK_EXPORTERS:
        reachable, url_msg = _check_endpoint(url)
        if not reachable:
            log.warning(f"Exporter {name!r} endpoint not reachable: {url_msg}")
            return ExporterStatus(exporter=name, active=False, collector_url=f"failed — {url_msg}")
    agent = get_agent(name)
    status = ExporterStatus(exporter=name, active=agent.tracing_active, collector_url=url)
    log.info(f"Exporter activated: {name} (active={status.active}, url={status.collector_url})")
    return status


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    session_id = request.session_id or str(uuid.uuid4())
    log.info(f"[{request.exporter}] session={session_id} Query: {request.query[:120]!r}")
    t0 = time.perf_counter()
    state = get_agent(request.exporter).run_turn(request.query, session_id=session_id)
    elapsed = time.perf_counter() - t0
    evaluation = state["evaluation"]
    log.info(f"[{request.exporter}] session={session_id} Done in {elapsed:.2f}s — faithfulness={evaluation.get('faithfulness', 0):.2f} hitl={state['hitl_required']}")
    return ChatResponse(
        final_answer=state["final_answer"],
        faithfulness=evaluation.get("faithfulness", 0.0),
        hitl_required=state["hitl_required"],
    )
