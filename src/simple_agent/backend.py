"""FastAPI backend for SimpleAgent — exposes POST /chat."""

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from .agent import build_agent, main, SimpleAgent
from .config import AgentConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("simple_agent.backend")

ExporterName = Literal["langfuse", "phoenix", "opik", "otel-stdout", "none"]

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
        log.info("Initialising agent  exporter=%r", exporter)
        log.info("Collector URL      : %s", EXPORTER_URLS.get(exporter, "unknown"))
        agent = build_agent(config=AgentConfig(exporter=exporter))
        log.info("Exporter active    : %s", agent._exporter is not None)
        log.info("─" * 60)
        _agents[exporter] = agent
    return _agents[exporter]


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("=" * 60)
    log.info("Simple Agent backend starting")
    log.info("Available exporters: %s", list(EXPORTER_URLS.keys()))
    log.info("Langfuse  → %s", EXPORTER_URLS["langfuse"])
    log.info("Phoenix   → %s", EXPORTER_URLS["phoenix"])
    log.info("Opik      → %s", EXPORTER_URLS["opik"])
    log.info("Default exporter: none")
    log.info("=" * 60)
    yield
    log.info("Simple Agent backend shutting down. Active exporters: %s", list(_agents.keys()))


app = FastAPI(title="Simple Agent API", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str
    exporter: ExporterName = "none"


class ChatResponse(BaseModel):
    response: str


class ExporterStatus(BaseModel):
    exporter: str
    active: bool
    collector_url: str


@app.post("/exporter/{name}", response_model=ExporterStatus)
def activate_exporter(name: ExporterName) -> ExporterStatus:
    """Pre-initialise and activate the selected exporter."""
    url = EXPORTER_URLS.get(name, "—")

    if name in _NETWORK_EXPORTERS:
        reachable, url_msg = _check_endpoint(url)
        if not reachable:
            log.warning("Exporter %r endpoint not reachable: %s", name, url_msg)
            return ExporterStatus(exporter=name, active=False, collector_url=f"failed — {url_msg}")

    agent = get_agent(name)
    status = ExporterStatus(
        exporter=name,
        active=agent._exporter is not None,
        collector_url=url,
    )
    log.info("Exporter activated: %s (active=%s, url=%s)", name, status.active, status.collector_url)
    return status


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    log.info("[%s] Received: %r", request.exporter, request.message)
    t0 = time.perf_counter()
    response = main(request.message, agent=get_agent(request.exporter))
    log.info("[%s] Done in %.2fs", request.exporter, time.perf_counter() - t0)
    return ChatResponse(response=response)
