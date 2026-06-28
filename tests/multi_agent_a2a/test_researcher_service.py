"""Tests for ResearcherExecutor (A2A executor wrapping ResearcherAgent).

The executor is tested by calling execute() directly with a fake RequestContext
and a collecting EventQueue — no real HTTP server needed, matching the spirit
of v1's agent-level unit tests.
"""

import types
from typing import Any

from langchain_core.messages import AIMessage

from a2a.helpers import new_data_message, new_data_part, get_data_parts
from a2a.helpers import new_task_from_user_message
from a2a.server.tasks import TaskUpdater
from a2a.types import Role, TaskState

from src.multi_agent.config import MultiAgentConfig
from src.multi_agent.researcher import ResearcherAgent
from src.multi_agent_a2a.researcher_service import ResearcherExecutor

NO_TRACE = MultiAgentConfig(exporter="none")


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class _FakeLLM:
    def __init__(self, json_response: str):
        self._json = json_response

    def invoke(self, messages: Any, **kwargs) -> AIMessage:
        return AIMessage(content=self._json)


def _fake_search(query: str, max_results: int = 3) -> list[dict]:
    return [{"title": "T", "url": "https://example.com", "snippet": f"about {query}"}]


def _fake_fetch(url: str, max_chars: int = 1500) -> str:
    return f"content of {url}"[:max_chars]


class _CollectingQueue:
    """Minimal async event queue that records everything enqueued."""

    def __init__(self):
        self.events: list = []

    async def enqueue_event(self, event) -> None:
        self.events.append(event)


def _make_context(payload: dict):
    """Build a duck-typed RequestContext with the given data payload."""
    message = new_data_message(data=payload, role=Role.ROLE_USER)
    ctx = types.SimpleNamespace(message=message, current_task=None)
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_researcher_executor_returns_completed_task():
    llm = _FakeLLM('{"summary": "AI tools in 2025.", "sources": [{"url": "https://example.com", "excerpt": "info"}]}')
    agent = ResearcherAgent(model=llm, search_fn=_fake_search, fetch_fn=_fake_fetch, config=NO_TRACE)
    executor = ResearcherExecutor(agent)

    queue = _CollectingQueue()
    ctx = _make_context({"query": "AI observability tools"})
    await executor.execute(ctx, queue)

    states = [e.status.state for e in queue.events if hasattr(e, "status")]
    assert TaskState.TASK_STATE_COMPLETED in states


async def test_researcher_executor_emits_artifact_with_result_and_trace_events():
    llm = _FakeLLM('{"summary": "Test summary.", "sources": [{"url": "https://x.com", "excerpt": "x"}]}')
    agent = ResearcherAgent(model=llm, search_fn=_fake_search, fetch_fn=_fake_fetch, config=NO_TRACE)
    executor = ResearcherExecutor(agent)

    queue = _CollectingQueue()
    ctx = _make_context({"query": "test query"})
    await executor.execute(ctx, queue)

    artifact_events = [e for e in queue.events if hasattr(e, "artifact")]
    assert len(artifact_events) >= 1
    data = get_data_parts(artifact_events[0].artifact.parts)[0]
    assert "result" in data
    assert "trace_events" in data
    assert data["result"]["summary"] == "Test summary."


async def test_researcher_executor_propagates_query_to_agent():
    queries_seen: list[str] = []

    class _TrackingAgent:
        def run(self, query: str, callback=None):
            queries_seen.append(query)
            return {"summary": "ok", "sources": []}, []

    executor = ResearcherExecutor(_TrackingAgent())  # type: ignore[arg-type]
    queue = _CollectingQueue()
    ctx = _make_context({"query": "my specific query"})
    await executor.execute(ctx, queue)

    assert queries_seen == ["my specific query"]
