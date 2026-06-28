"""Integration test: full A2A round-trip using real HTTP wire transport.

Starts both Researcher and Evaluator FastAPI apps in-process using
uvicorn.Server threads, then drives OrchestratorAgentA2A against them.
Fake LLM models are injected into the underlying agents so no API keys
or real network calls are needed — only the A2A JSON-RPC transport is real.
"""

import threading
import time
from typing import Any

import httpx
import pytest
import uvicorn
from langchain_core.messages import AIMessage

from src.multi_agent.config import MultiAgentConfig
from src.multi_agent.researcher import ResearcherAgent
from src.multi_agent.state import EvaluationResult, ResearchResult
from src.multi_agent_a2a.config import MultiAgentA2AConfig
from src.multi_agent_a2a.evaluator_service import build_app as build_evaluator_app
from src.multi_agent_a2a.orchestrator import OrchestratorAgentA2A
from src.multi_agent_a2a.researcher_service import build_app as build_researcher_app

# Use high test ports to avoid clashing with real running services
_RESEARCHER_PORT = 18011
_EVALUATOR_PORT  = 18012


# ---------------------------------------------------------------------------
# Fake agents with injected fakes (no API calls)
# ---------------------------------------------------------------------------

class _FakeResearcherLLM:
    def invoke(self, messages: Any, **kwargs) -> AIMessage:
        return AIMessage(content='{"summary": "Test summary from fake researcher.", "sources": [{"url": "https://example.com", "excerpt": "test excerpt"}]}')


class _FakeFaithfulnessEvaluator:
    """Synchronous duck-typed fake for FaithfulnessEvaluator."""
    def run(self, query: str, research: ResearchResult, callback=None):
        from src.multi_agent.state import make_event
        result: EvaluationResult = {
            "faithfulness": 0.9, "completeness": 0.0,
            "guardrail_compliance": 1.0, "label": "grounded",
            "raw_response": '{"faithfulness": 0.9, "label": "grounded", "reason": "All claims supported."}',
        }
        events = [make_event("evaluator", "evaluation", {"faithfulness": 0.9})]
        return result, events


class _FakeOrchestratorLLM:
    def invoke(self, messages: Any, **kwargs) -> AIMessage:
        return AIMessage(content="Integration test final answer.")


def _fake_search(query: str, max_results: int = 3) -> list[dict]:
    return [{"title": "T", "url": "https://example.com", "snippet": f"about {query}"}]


def _fake_fetch(url: str, max_chars: int = 1500) -> str:
    return "page content"


# ---------------------------------------------------------------------------
# Server fixture: start both services once per module
# ---------------------------------------------------------------------------

def _wait_for_service(port: int, timeout: float = 10.0) -> None:
    url = f"http://127.0.0.1:{port}/.well-known/agent.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(url, timeout=1)
            return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f"Service on port {port} did not start within {timeout}s")


@pytest.fixture(scope="module")
def a2a_services():
    """Start Researcher and Evaluator A2A services in background threads."""
    no_trace = MultiAgentConfig(exporter="none")

    researcher_agent = ResearcherAgent(
        model=_FakeResearcherLLM(),
        search_fn=_fake_search,
        fetch_fn=_fake_fetch,
        config=no_trace,
    )
    evaluator_agent = _FakeFaithfulnessEvaluator()

    researcher_app = build_researcher_app(agent=researcher_agent, port=_RESEARCHER_PORT)
    evaluator_app  = build_evaluator_app(agent=evaluator_agent,  port=_EVALUATOR_PORT)

    def _run(app, port):
        cfg = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="error")
        uvicorn.Server(cfg).run()

    t1 = threading.Thread(target=_run, args=(researcher_app, _RESEARCHER_PORT), daemon=True)
    t2 = threading.Thread(target=_run, args=(evaluator_app,  _EVALUATOR_PORT),  daemon=True)
    t1.start()
    t2.start()

    _wait_for_service(_RESEARCHER_PORT)
    _wait_for_service(_EVALUATOR_PORT)

    yield

    # daemon threads exit automatically when the test process ends


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_full_a2a_roundtrip_returns_answer(a2a_services):
    config = MultiAgentA2AConfig(
        exporter="none",
        researcher_url=f"http://127.0.0.1:{_RESEARCHER_PORT}",
        evaluator_url=f"http://127.0.0.1:{_EVALUATOR_PORT}",
    )
    orchestrator = OrchestratorAgentA2A(model=_FakeOrchestratorLLM(), config=config)
    state = await orchestrator.run("What are LLM observability tools?")

    assert state["final_answer"].startswith("Integration test final answer.")
    assert "[1] https://example.com" in state["final_answer"]
    assert state["hitl_required"] is False
    assert state["evaluation"]["faithfulness"] == 0.9


async def test_full_a2a_roundtrip_trace_events_span_all_agents(a2a_services):
    config = MultiAgentA2AConfig(
        exporter="none",
        researcher_url=f"http://127.0.0.1:{_RESEARCHER_PORT}",
        evaluator_url=f"http://127.0.0.1:{_EVALUATOR_PORT}",
    )
    orchestrator = OrchestratorAgentA2A(model=_FakeOrchestratorLLM(), config=config)
    state = await orchestrator.run("Tell me about AI agents.")

    agents_seen = {e["agent"] for e in state["trace_events"]}
    assert "orchestrator" in agents_seen
    assert "researcher"   in agents_seen
    assert "evaluator"    in agents_seen


async def test_full_a2a_roundtrip_research_result_propagates(a2a_services):
    config = MultiAgentA2AConfig(
        exporter="none",
        researcher_url=f"http://127.0.0.1:{_RESEARCHER_PORT}",
        evaluator_url=f"http://127.0.0.1:{_EVALUATOR_PORT}",
    )
    orchestrator = OrchestratorAgentA2A(model=_FakeOrchestratorLLM(), config=config)
    state = await orchestrator.run("query")

    assert state["research"]["summary"] == "Test summary from fake researcher."
    assert len(state["research"]["sources"]) == 1
