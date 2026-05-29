"""FastAPI backend for the multi-agent Research & Fact-Check system."""

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from .orchestrator import OrchestratorAgent
from .config import MultiAgentConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("multi_agent.backend")

ExporterName = Literal["langfuse", "phoenix", "opik", "otel-stdout", "none"]

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
        log.info("Initialising OrchestratorAgent  exporter=%r", exporter)
        log.info("Collector URL                  : %s", EXPORTER_URLS.get(exporter, "unknown"))
        agent = OrchestratorAgent(config=MultiAgentConfig(exporter=exporter))
        log.info("Exporter active                : %s", agent._adapter.active)
        log.info("─" * 60)
        _agents[exporter] = agent
    return _agents[exporter]


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=" * 60)
    log.info("Multi-Agent backend starting")
    log.info("Langfuse  → %s", EXPORTER_URLS["langfuse"])
    log.info("Phoenix   → %s", EXPORTER_URLS["phoenix"])
    log.info("Opik      → %s", EXPORTER_URLS["opik"])
    log.info("Default exporter: none")
    log.info("=" * 60)
    yield
    log.info("Multi-Agent backend shutting down. Active exporters: %s", list(_agents.keys()))


app = FastAPI(title="Multi-Agent Research API", lifespan=lifespan)


class ChatRequest(BaseModel):
    query: str
    exporter: ExporterName = "none"
    session_id: str = ""


class ChatResponse(BaseModel):
    final_answer: str
    faithfulness: float
    completeness: float
    guardrail_compliance: float
    label: str
    retry_count: int
    hitl_required: bool


class ExporterStatus(BaseModel):
    exporter: str
    active: bool
    collector_url: str


@app.delete("/session/{session_id}", status_code=204)
def reset_session(session_id: str) -> None:
    """Discard the conversation history for *session_id* on all active agents."""
    for agent in _agents.values():
        agent.reset_history(session_id)
    log.info("Conversation history reset for session=%s", session_id)


@app.post("/exporter/{name}", response_model=ExporterStatus)
def activate_exporter(name: ExporterName) -> ExporterStatus:
    url = EXPORTER_URLS.get(name, "—")
    if name in _NETWORK_EXPORTERS:
        reachable, url_msg = _check_endpoint(url)
        if not reachable:
            log.warning("Exporter %r endpoint not reachable: %s", name, url_msg)
            return ExporterStatus(exporter=name, active=False, collector_url=f"failed — {url_msg}")
    agent = get_agent(name)
    status = ExporterStatus(exporter=name, active=agent._adapter.active, collector_url=url)
    log.info("Exporter activated: %s (active=%s, url=%s)", name, status.active, status.collector_url)
    return status


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    session_id = request.session_id or str(uuid.uuid4())
    log.info("[%s] session=%s Query: %r", request.exporter, session_id, request.query[:120])
    t0 = time.perf_counter()
    # run_turn maintains per-session conversation history; a stable session_id
    # across requests enables multi-turn follow-up questions.
    state = get_agent(request.exporter).run_turn(request.query, session_id=session_id)
    elapsed = time.perf_counter() - t0
    evaluation = state["evaluation"]
    log.info("[%s] session=%s Done in %.2fs — faithfulness=%.2f hitl=%s",
             request.exporter, session_id, elapsed, evaluation.get("faithfulness", 0), state["hitl_required"])
    return ChatResponse(
        final_answer=state["final_answer"],
        faithfulness=evaluation.get("faithfulness", 0.0),
        completeness=evaluation.get("completeness", 0.0),
        guardrail_compliance=evaluation.get("guardrail_compliance", 0.0),
        label=evaluation.get("label", "unknown"),
        retry_count=state["retry_count"],
        hitl_required=state["hitl_required"],
    )
