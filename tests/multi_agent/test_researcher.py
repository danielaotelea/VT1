"""Tests for ResearcherAgent.

All tests inject fake search_fn, fetch_fn, and model so no API keys are needed.
"""

from typing import Any
from langchain_core.messages import AIMessage

from src.multi_agent.config import MultiAgentConfig
from src.multi_agent.researcher import ResearcherAgent

NO_TRACE = MultiAgentConfig(exporter="none")


# ---------------------------------------------------------------------------
# Fake helpers
# ---------------------------------------------------------------------------

def _fake_search(query: str, max_results: int = 3) -> list[dict]:
    """Return a fixed set of search results."""
    return [
        {"title": "Example Domain", "url": "https://example.com", "snippet": "Useful info about " + query},
        {"title": "Another Result", "url": "https://example.org", "snippet": "More info about " + query},
    ]


def _fake_fetch(url: str, max_chars: int = 1_500) -> str:
    return f"Page content for {url}"[:max_chars]


class _FakeLLM:
    """Returns a canned JSON response regardless of input."""

    def __init__(self, response_json: str):
        self._response_json = response_json

    def invoke(self, messages: Any) -> AIMessage:
        return AIMessage(content=self._response_json)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_researcher_returns_result_and_events():
    model = _FakeLLM('{"summary": "LLM observability tools in 2025 include Langfuse and Arize.", "sources": [{"url": "https://example.com", "excerpt": "Useful info"}]}')
    agent = ResearcherAgent(model=model, search_fn=_fake_search, fetch_fn=_fake_fetch, config=NO_TRACE)
    result, events = agent.run("What are LLM observability tools?")

    assert result["summary"] != ""
    assert isinstance(result["sources"], list)
    assert len(events) > 0


def test_researcher_emits_tool_call_events():
    model = _FakeLLM('{"summary": "Summary.", "sources": []}')
    agent = ResearcherAgent(model=model, search_fn=_fake_search, fetch_fn=_fake_fetch, config=NO_TRACE)
    _, events = agent.run("test query")

    event_types = [e["event_type"] for e in events]
    assert "tool_call" in event_types
    assert "llm_response" in event_types


def test_researcher_emits_web_search_event():
    model = _FakeLLM('{"summary": "Summary.", "sources": []}')
    agent = ResearcherAgent(model=model, search_fn=_fake_search, fetch_fn=_fake_fetch, config=NO_TRACE)
    _, events = agent.run("test query")

    web_search_events = [e for e in events if e.get("payload", {}).get("tool") == "web_search"]
    assert len(web_search_events) == 1
    assert web_search_events[0]["payload"]["query"] == "test query"


def test_researcher_emits_fetch_page_events():
    model = _FakeLLM('{"summary": "Summary.", "sources": []}')
    agent = ResearcherAgent(model=model, search_fn=_fake_search, fetch_fn=_fake_fetch, config=NO_TRACE)
    _, events = agent.run("test query")

    fetch_events = [e for e in events if e.get("payload", {}).get("tool") == "fetch_page"]
    # _fake_search returns 2 results with valid URLs → 2 fetch_page events
    assert len(fetch_events) == 2


def test_researcher_handles_malformed_json_gracefully():
    """When the LLM returns non-JSON, the raw text becomes the summary."""
    model = _FakeLLM("Sorry, I cannot answer that.")
    agent = ResearcherAgent(model=model, search_fn=_fake_search, fetch_fn=_fake_fetch, config=NO_TRACE)
    result, _ = agent.run("test query")

    assert result["summary"] == "Sorry, I cannot answer that."
    assert result["sources"] == []


def test_researcher_respects_max_search_results():
    call_log: list[int] = []

    def counting_search(query: str, max_results: int) -> list[dict]:
        call_log.append(max_results)
        return []

    model = _FakeLLM('{"summary": "Empty.", "sources": []}')
    config = MultiAgentConfig(exporter="none", max_search_results=5)
    agent = ResearcherAgent(model=model, search_fn=counting_search, fetch_fn=_fake_fetch, config=config)
    agent.run("query")

    assert call_log[0] == 5


def test_researcher_skips_fetch_for_empty_url():
    """Results without a URL should not trigger fetch_page."""
    fetch_log: list[str] = []

    def logging_fetch(url: str, max_chars: int) -> str:
        fetch_log.append(url)
        return "content"

    def search_no_url(query: str, max_results: int) -> list[dict]:
        return [{"title": "No URL result", "url": "", "snippet": "content"}]

    model = _FakeLLM('{"summary": "Ok.", "sources": []}')
    agent = ResearcherAgent(model=model, search_fn=search_no_url, fetch_fn=logging_fetch, config=NO_TRACE)
    agent.run("query")

    assert fetch_log == []


def test_researcher_all_trace_events_have_required_fields():
    model = _FakeLLM('{"summary": "Summary.", "sources": []}')
    agent = ResearcherAgent(model=model, search_fn=_fake_search, fetch_fn=_fake_fetch, config=NO_TRACE)
    _, events = agent.run("query")

    for event in events:
        assert "timestamp" in event
        assert "agent" in event
        assert event["agent"] == "researcher"
        assert "event_type" in event
        assert "payload" in event
