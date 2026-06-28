"""Tests for OrchestratorAgentA2A.

All tests inject a fake call_agent_fn so no real network calls or API keys
are needed — mirrors the injected-dependency pattern used by v1's
test_orchestrator.py with its fake Researcher/Evaluator objects.
"""

import pytest
from datetime import datetime, timezone
from langchain_core.messages import AIMessage
from typing import Any

from src.multi_agent.state import EvaluationResult, ResearchResult, TraceEvent
from src.multi_agent_a2a.config import MultiAgentA2AConfig
from src.multi_agent_a2a.orchestrator import LoopDetectedError, OrchestratorAgentA2A, PIIExposureError

NO_TRACE = MultiAgentA2AConfig(exporter="none")


# ---------------------------------------------------------------------------
# Fake helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


_GOOD_RESEARCH: ResearchResult = {
    "summary": "Summary of research.",
    "sources": [{"url": "https://example.com", "excerpt": "relevant excerpt"}],
}
_HIGH_EVAL: EvaluationResult = {
    "faithfulness": 0.95, "label": "grounded", "raw_response": "", "reason": "",
}
_LOW_EVAL: EvaluationResult = {
    "faithfulness": 0.3, "label": "hallucinated", "raw_response": "", "reason": "",
}


def _research_event() -> TraceEvent:
    return TraceEvent(timestamp=_ts(), agent="researcher", event_type="llm_response", payload={})


def _eval_event(faithfulness: float) -> TraceEvent:
    return TraceEvent(timestamp=_ts(), agent="evaluator", event_type="evaluation", payload={"faithfulness": faithfulness})


class _FakeLLM:
    def __init__(self, answer: str = "Final synthesised answer."):
        self._answer = answer

    def invoke(self, messages: Any, **kwargs) -> AIMessage:
        return AIMessage(content=self._answer)


def _make_call_agent(research: ResearchResult, evaluation: EvaluationResult):
    """Returns a fake call_agent_fn that routes by URL."""
    async def _call(url: str, payload: dict, headers: dict | None = None):
        if "8011" in url:  # researcher
            return research, [_research_event()]
        else:              # evaluator
            return evaluation, [_eval_event(evaluation["faithfulness"])]
    return _call


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

async def test_orchestrator_a2a_returns_final_answer():
    agent = OrchestratorAgentA2A(
        model=_FakeLLM("The answer."),
        config=NO_TRACE,
        call_agent_fn=_make_call_agent(_GOOD_RESEARCH, _HIGH_EVAL),
    )
    state = await agent.run("What is X?")

    assert state["final_answer"].startswith("The answer.")
    assert "[1] https://example.com" in state["final_answer"]
    assert state["hitl_required"] is False


async def test_orchestrator_a2a_state_has_research_and_evaluation():
    agent = OrchestratorAgentA2A(
        model=_FakeLLM(),
        config=NO_TRACE,
        call_agent_fn=_make_call_agent(_GOOD_RESEARCH, _HIGH_EVAL),
    )
    state = await agent.run("query")

    assert state["research"]["summary"] == _GOOD_RESEARCH["summary"]
    assert state["evaluation"]["faithfulness"] == _HIGH_EVAL["faithfulness"]


async def test_orchestrator_a2a_trace_events_span_all_agents():
    agent = OrchestratorAgentA2A(
        model=_FakeLLM(),
        config=NO_TRACE,
        call_agent_fn=_make_call_agent(_GOOD_RESEARCH, _HIGH_EVAL),
    )
    state = await agent.run("query")

    agents_seen = {e["agent"] for e in state["trace_events"]}
    assert "orchestrator" in agents_seen
    assert "researcher" in agents_seen
    assert "evaluator" in agents_seen


# ---------------------------------------------------------------------------
# Retry / low-confidence path
# ---------------------------------------------------------------------------

async def test_orchestrator_a2a_retries_on_low_confidence():
    call_counts = {"n": 0}

    async def _call(url: str, payload: dict, headers: dict | None = None):
        if "8011" in url:
            call_counts["n"] += 1
            return _GOOD_RESEARCH, [_research_event()]
        score = 0.9 if call_counts["n"] > 1 else 0.3
        label = "grounded" if score > 0.6 else "hallucinated"
        eval_result: EvaluationResult = {
            "faithfulness": score, "label": label, "raw_response": "", "reason": "",
        }
        return eval_result, [_eval_event(score)]

    config = MultiAgentA2AConfig(exporter="none", max_evaluator_retries=2, low_confidence_threshold=0.6)
    agent = OrchestratorAgentA2A(model=_FakeLLM(), config=config, call_agent_fn=_call)
    state = await agent.run("query")

    assert state["hitl_required"] is False
    assert call_counts["n"] >= 2


async def test_orchestrator_a2a_escalates_to_hitl_after_max_retries():
    config = MultiAgentA2AConfig(exporter="none", max_evaluator_retries=1, low_confidence_threshold=0.6)
    agent = OrchestratorAgentA2A(
        model=_FakeLLM(),
        config=config,
        call_agent_fn=_make_call_agent(_GOOD_RESEARCH, _LOW_EVAL),
    )
    state = await agent.run("query")

    assert state["hitl_required"] is True
    hitl_events = [e for e in state["trace_events"] if e.get("payload", {}).get("guard") == "hitl_escalation"]
    assert len(hitl_events) == 1


async def test_orchestrator_a2a_retry_count_in_state():
    config = MultiAgentA2AConfig(exporter="none", max_evaluator_retries=2, low_confidence_threshold=0.6)
    agent = OrchestratorAgentA2A(
        model=_FakeLLM(),
        config=config,
        call_agent_fn=_make_call_agent(_GOOD_RESEARCH, _LOW_EVAL),
    )
    state = await agent.run("query")

    assert state["retry_count"] == 3


# ---------------------------------------------------------------------------
# Safety guards
# ---------------------------------------------------------------------------

async def test_orchestrator_a2a_raises_pii_error():
    pii_research: ResearchResult = {
        "summary": "API key is sk-abc123def456ghi789jkl012mno345",
        "sources": [],
    }
    agent = OrchestratorAgentA2A(
        model=_FakeLLM(),
        config=NO_TRACE,
        call_agent_fn=_make_call_agent(pii_research, _HIGH_EVAL),
    )
    with pytest.raises(PIIExposureError):
        await agent.run("query")


async def test_orchestrator_a2a_raises_loop_detection_error():
    config = MultiAgentA2AConfig(exporter="none", max_identical_tool_calls=1, low_confidence_threshold=0.6)
    agent = OrchestratorAgentA2A(
        model=_FakeLLM(),
        config=config,
        call_agent_fn=_make_call_agent(_GOOD_RESEARCH, _LOW_EVAL),
    )
    with pytest.raises(LoopDetectedError):
        await agent.run("same query")


async def test_orchestrator_a2a_emits_low_confidence_guard_events():
    config = MultiAgentA2AConfig(exporter="none", max_evaluator_retries=1, low_confidence_threshold=0.6)
    agent = OrchestratorAgentA2A(
        model=_FakeLLM(),
        config=config,
        call_agent_fn=_make_call_agent(_GOOD_RESEARCH, _LOW_EVAL),
    )
    state = await agent.run("query")

    guard_events = [
        e for e in state["trace_events"]
        if e.get("payload", {}).get("guard") == "low_confidence"
    ]
    assert len(guard_events) >= 1
