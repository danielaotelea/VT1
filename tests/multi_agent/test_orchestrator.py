"""Tests for OrchestratorAgent.

All tests inject fake Researcher, Evaluator, and model so no API keys are needed.
"""

from typing import Any
from langchain_core.messages import AIMessage

from src.multi_agent.config import MultiAgentConfig
from src.multi_agent.orchestrator import LoopDetectedError, OrchestratorAgent, PIIExposureError
from src.multi_agent.state import EvaluationResult, ResearchResult

NO_TRACE = MultiAgentConfig(exporter="none")


# ---------------------------------------------------------------------------
# Fake agents / models
# ---------------------------------------------------------------------------

class _FakeResearcher:
    """Returns a fixed ResearchResult."""

    def __init__(self, result: ResearchResult):
        self._result = result

    def run(self, query: str, callback=None):  # type: ignore[override]
        from datetime import datetime, timezone
        from src.multi_agent.state import TraceEvent
        event = TraceEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent="researcher",
            event_type="llm_response",
            payload={"query": query},
        )
        return self._result, [event]


class _FakeEvaluator:
    """Returns a fixed EvaluationResult."""

    def __init__(self, result: EvaluationResult):
        self._result = result

    def run(self, query: str, research: ResearchResult, callback=None):  # type: ignore[override]
        from datetime import datetime, timezone
        from src.multi_agent.state import TraceEvent
        event = TraceEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            agent="evaluator",
            event_type="evaluation",
            payload={"faithfulness": self._result["faithfulness"]},
        )
        return self._result, [event]


class _FakeLLM:
    def __init__(self, answer: str = "Final synthesised answer."):
        self._answer = answer

    def invoke(self, messages: Any) -> AIMessage:
        return AIMessage(content=self._answer)


_GOOD_RESEARCH: ResearchResult = {
    "summary": "Summary of research.",
    "sources": [{"url": "https://example.com", "excerpt": "relevant excerpt"}],
}

_HIGH_EVAL: EvaluationResult = {
    "faithfulness": 0.95,
    "completeness": 0.9,
    "guardrail_compliance": 1.0,
    "label": "grounded",
    "raw_response": '{"faithfulness": 0.95}',
}

_LOW_EVAL: EvaluationResult = {
    "faithfulness": 0.3,
    "completeness": 0.5,
    "guardrail_compliance": 1.0,
    "label": "hallucinated",
    "raw_response": '{"faithfulness": 0.3}',
}


# ---------------------------------------------------------------------------
# Tests — happy path
# ---------------------------------------------------------------------------

def test_orchestrator_returns_final_answer():
    agent = OrchestratorAgent(
        researcher=_FakeResearcher(_GOOD_RESEARCH),
        evaluator=_FakeEvaluator(_HIGH_EVAL),
        model=_FakeLLM("The answer is X."),
        config=NO_TRACE,
    )
    state = agent.run("What is X?")

    assert state["final_answer"] == "The answer is X."
    assert state["hitl_required"] is False


def test_orchestrator_state_contains_research_and_evaluation():
    agent = OrchestratorAgent(
        researcher=_FakeResearcher(_GOOD_RESEARCH),
        evaluator=_FakeEvaluator(_HIGH_EVAL),
        model=_FakeLLM(),
        config=NO_TRACE,
    )
    state = agent.run("query")

    assert state["research"]["summary"] == _GOOD_RESEARCH["summary"]
    assert state["evaluation"]["faithfulness"] == _HIGH_EVAL["faithfulness"]


def test_orchestrator_state_has_trace_events():
    agent = OrchestratorAgent(
        researcher=_FakeResearcher(_GOOD_RESEARCH),
        evaluator=_FakeEvaluator(_HIGH_EVAL),
        model=_FakeLLM(),
        config=NO_TRACE,
    )
    state = agent.run("query")

    assert len(state["trace_events"]) > 0
    agents_seen = {e["agent"] for e in state["trace_events"]}
    # Orchestrator, researcher, and evaluator events all aggregated
    assert "orchestrator" in agents_seen
    assert "researcher" in agents_seen
    assert "evaluator" in agents_seen


# ---------------------------------------------------------------------------
# Tests — retry / low-confidence path
# ---------------------------------------------------------------------------

def test_orchestrator_retries_on_low_confidence():
    call_counts = {"n": 0}
    _GOOD_RESEARCH_2: ResearchResult = {**_GOOD_RESEARCH, "summary": "Retry summary."}

    class _CountingResearcher:
        def run(self, query: str, callback=None):
            call_counts["n"] += 1
            from datetime import datetime, timezone
            from src.multi_agent.state import TraceEvent
            return _GOOD_RESEARCH_2, [TraceEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                agent="researcher", event_type="llm_response", payload={},
            )]

    class _EscalatingEvaluator:
        """Returns low score for first call, high score thereafter."""
        def __init__(self):
            self._calls = 0

        def run(self, query: str, research: ResearchResult, callback=None):
            self._calls += 1
            from datetime import datetime, timezone
            from src.multi_agent.state import TraceEvent
            score = 0.9 if self._calls > 1 else 0.3
            label = "grounded" if score > 0.6 else "hallucinated"
            result: EvaluationResult = {
                "faithfulness": score, "completeness": 0.8,
                "guardrail_compliance": 1.0, "label": label, "raw_response": "",
            }
            return result, [TraceEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                agent="evaluator", event_type="evaluation", payload={"faithfulness": score},
            )]

    config = MultiAgentConfig(exporter="none", max_evaluator_retries=2, low_confidence_threshold=0.6)
    agent = OrchestratorAgent(
        researcher=_CountingResearcher(),
        evaluator=_EscalatingEvaluator(),
        model=_FakeLLM(),
        config=config,
    )
    state = agent.run("query")

    assert state["hitl_required"] is False
    # Researcher called at least twice (initial + 1 retry)
    assert call_counts["n"] >= 2


def test_orchestrator_escalates_to_hitl_after_max_retries():
    config = MultiAgentConfig(exporter="none", max_evaluator_retries=1, low_confidence_threshold=0.6)
    agent = OrchestratorAgent(
        researcher=_FakeResearcher(_GOOD_RESEARCH),
        evaluator=_FakeEvaluator(_LOW_EVAL),
        model=_FakeLLM(),
        config=config,
    )
    state = agent.run("query")

    assert state["hitl_required"] is True
    hitl_events = [e for e in state["trace_events"] if e.get("payload", {}).get("guard") == "hitl_escalation"]
    assert len(hitl_events) == 1


def test_orchestrator_retry_count_in_state():
    config = MultiAgentConfig(exporter="none", max_evaluator_retries=2, low_confidence_threshold=0.6)
    agent = OrchestratorAgent(
        researcher=_FakeResearcher(_GOOD_RESEARCH),
        evaluator=_FakeEvaluator(_LOW_EVAL),
        model=_FakeLLM(),
        config=config,
    )
    state = agent.run("query")

    # After max_evaluator_retries=2, retry_count should be 3 (initial + 2 retries)
    assert state["retry_count"] == 3


# ---------------------------------------------------------------------------
# Tests — safety guards
# ---------------------------------------------------------------------------

def test_orchestrator_raises_pii_error_on_credential_in_summary():
    pii_research: ResearchResult = {
        "summary": "The API key is sk-abc123def456ghi789jkl012mno345",
        "sources": [],
    }
    agent = OrchestratorAgent(
        researcher=_FakeResearcher(pii_research),
        evaluator=_FakeEvaluator(_HIGH_EVAL),
        model=_FakeLLM(),
        config=NO_TRACE,
    )
    import pytest
    with pytest.raises(PIIExposureError):
        agent.run("query")


def test_orchestrator_emits_loop_detection_guard_on_repeated_queries():
    """Loop detection triggers when the orchestrator's internal query counter exceeds the limit."""
    config = MultiAgentConfig(exporter="none", max_identical_tool_calls=1, low_confidence_threshold=0.6)
    agent = OrchestratorAgent(
        researcher=_FakeResearcher(_GOOD_RESEARCH),
        evaluator=_FakeEvaluator(_LOW_EVAL),
        model=_FakeLLM(),
        config=config,
    )
    import pytest
    with pytest.raises(LoopDetectedError):
        agent.run("same query")


def test_orchestrator_emits_low_confidence_guard_events():
    config = MultiAgentConfig(exporter="none", max_evaluator_retries=1, low_confidence_threshold=0.6)
    agent = OrchestratorAgent(
        researcher=_FakeResearcher(_GOOD_RESEARCH),
        evaluator=_FakeEvaluator(_LOW_EVAL),
        model=_FakeLLM(),
        config=config,
    )
    state = agent.run("query")

    guard_events = [
        e for e in state["trace_events"]
        if e.get("payload", {}).get("guard") == "low_confidence"
    ]
    assert len(guard_events) >= 1
