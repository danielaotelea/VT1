"""FastAPI backend for SimpleAgent — exposes POST /chat."""

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from .agent import SimpleAgent, build_agent, main
from .config import AgentConfig, ExporterName

load_dotenv()

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("simple_agent.backend")

_agents: dict[str, SimpleAgent] = {}

EXPORTER_URLS: dict[str, str] = {
    "langfuse": os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
    "phoenix": os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006"),
    "opik": os.getenv("OPIK_URL_OVERRIDE", "http://localhost:5173/api").removesuffix("/api"),
    "otel-stdout": "stdout",
    "none": "—",
}

# Exporters that require a reachable HTTP endpoint before activation
_NETWORK_EXPORTERS = {"langfuse", "phoenix", "opik"}


def _check_endpoint(url: str) -> tuple[bool, str]:
    """Return (reachable, message) for the given base URL."""
    try:
        httpx.get(url, timeout=3)
        return True, url
    except Exception as e:
        return False, f"unreachable — {e}"


def get_agent(exporter: ExporterName) -> SimpleAgent:
    if exporter not in _agents:
        log.info("─" * 60)
        log.info(f"Initialising agent  exporter={exporter!r}")
        log.info(f"Collector URL      : {EXPORTER_URLS.get(exporter, 'unknown')}")
        agent = build_agent(config=AgentConfig(exporter=exporter))
        log.info(f"Exporter active    : {agent.tracing_active}")
        log.info("─" * 60)
        _agents[exporter] = agent
    return _agents[exporter]


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=" * 60)
    log.info("Simple Agent backend starting")
    log.info(f"Available exporters: {list(EXPORTER_URLS.keys())}")
    log.info(f"Langfuse  → {EXPORTER_URLS['langfuse']}")
    log.info(f"Phoenix   → {EXPORTER_URLS['phoenix']}")
    log.info(f"Opik      → {EXPORTER_URLS['opik']}")
    log.info("Default exporter: none")
    log.info("=" * 60)
    yield
    log.info(f"Simple Agent backend shutting down. Active exporters: {list(_agents.keys())}")


app = FastAPI(title="Simple Agent API", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str
    exporter: ExporterName = "none"
    session_id: str = ""


class ChatResponse(BaseModel):
    response: str


class ExporterStatus(BaseModel):
    exporter: str
    active: bool
    collector_url: str


@app.post("/exporter/{name}", response_model=ExporterStatus)
def activate_exporter(name: ExporterName) -> ExporterStatus:
    """Pre-initialize and activate the selected exporter."""
    url = EXPORTER_URLS.get(name, "—")

    if name in _NETWORK_EXPORTERS:
        reachable, url_msg = _check_endpoint(url)
        if not reachable:
            log.warning(f"Exporter {name!r} endpoint not reachable: {url_msg}")
            return ExporterStatus(exporter=name, active=False, collector_url=f"failed — {url_msg}")

    agent = get_agent(name)
    status = ExporterStatus(
        exporter=name,
        active=agent.tracing_active,
        collector_url=url,
    )
    log.info(f"Exporter activated: {name} (active={status.active}, url={status.collector_url})")
    return status


@app.delete("/session/{session_id}", status_code=200)
def close_session(session_id: str) -> dict:
    """Signal that a UI session is ending.

    The simple agent holds no per-session server state, so this is primarily
    a flush hook: if a Langfuse agent is active, its SDK buffer is flushed so
    all spans for the session are delivered before the next session starts.
    """
    log.info(f"Session closed: {session_id}")
    langfuse_agent = _agents.get("langfuse")
    if langfuse_agent is not None:
        adapter = langfuse_agent._adapter
        flush_fn = getattr(adapter, "flush", None) or getattr(
            getattr(adapter, "_client", None), "flush", None
        )
        if flush_fn is not None:
            try:
                flush_fn()
            except Exception as exc:
                log.warning(f"Langfuse flush failed for session {session_id}: {exc}")
    return {"closed": session_id}


@app.get("/health")
def health() -> dict:
    """Liveness probe — returns active exporters."""
    return {"status": "ok", "active_exporters": list(_agents.keys())}

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    session_id = request.session_id or str(uuid.uuid4())
    log.info(f"[{request.exporter}] session={session_id} Received: {request.message!r}")
    t0 = time.perf_counter()
    response = main(request.message, agent=get_agent(request.exporter), session_id=session_id)
    log.info(f"[{request.exporter}] session={session_id} Done in {time.perf_counter() - t0:.2f}s")
    return ChatResponse(response=response)
