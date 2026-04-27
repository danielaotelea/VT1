"""Tests for EvaluatorAgent.

All tests inject a fake model so no API keys are needed.
"""

from typing import Any
from langchain_core.messages import AIMessage

from src.multi_agent.config import MultiAgentConfig
from src.multi_agent.evaluator import EvaluatorAgent
from src.multi_agent.state import ResearchResult

NO_TRACE = MultiAgentConfig(exporter="none")

_GOOD_RESEARCH: ResearchResult = {
    "summary": "LLM observability tools include Langfuse, Arize Phoenix, and Comet Opik.",
    "sources": [
        {"url": "https://langfuse.com", "excerpt": "Langfuse is an open-source LLM observability platform."},
        {"url": "https://arize.com", "excerpt": "Arize Phoenix supports LLM tracing and evaluation."},
    ],
}


class _FakeLLM:
    def __init__(self, response_json: str):
        self._response_json = response_json

    def invoke(self, messages: Any) -> AIMessage:
        return AIMessage(content=self._response_json)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_evaluator_returns_grounded_result():
    model = _FakeLLM('{"faithfulness": 0.9, "completeness": 0.85, "guardrail_compliance": 1.0, "label": "grounded", "reasoning": "All claims cited."}')
    agent = EvaluatorAgent(model=model, config=NO_TRACE)
    result, events = agent.run("LLM observability tools?", _GOOD_RESEARCH)

    assert result["faithfulness"] == 0.9
    assert result["completeness"] == 0.85
    assert result["guardrail_compliance"] == 1.0
    assert result["label"] == "grounded"
    assert len(events) > 0


def test_evaluator_returns_hallucinated_label():
    model = _FakeLLM('{"faithfulness": 0.2, "completeness": 0.5, "guardrail_compliance": 1.0, "label": "hallucinated", "reasoning": "Claims not grounded."}')
    agent = EvaluatorAgent(model=model, config=NO_TRACE)
    result, _ = agent.run("query", _GOOD_RESEARCH)

    assert result["label"] == "hallucinated"
    assert result["faithfulness"] == 0.2


def test_evaluator_emits_evaluation_event():
    model = _FakeLLM('{"faithfulness": 0.9, "completeness": 0.9, "guardrail_compliance": 1.0, "label": "grounded", "reasoning": "ok"}')
    agent = EvaluatorAgent(model=model, config=NO_TRACE)
    _, events = agent.run("query", _GOOD_RESEARCH)

    eval_events = [e for e in events if e["event_type"] == "evaluation"]
    assert len(eval_events) == 1
    assert eval_events[0]["agent"] == "evaluator"


def test_evaluator_emits_warning_event_when_faithfulness_below_threshold():
    model = _FakeLLM('{"faithfulness": 0.7, "completeness": 0.8, "guardrail_compliance": 1.0, "label": "grounded", "reasoning": "mostly ok"}')
    config = MultiAgentConfig(exporter="none", faithfulness_threshold=0.8)
    agent = EvaluatorAgent(model=model, config=config)
    _, events = agent.run("query", _GOOD_RESEARCH)

    guard_events = [e for e in events if e["event_type"] == "guard_triggered"]
    assert len(guard_events) == 1
    assert guard_events[0]["payload"]["guard"] == "low_faithfulness"


def test_evaluator_no_warning_when_faithfulness_above_threshold():
    model = _FakeLLM('{"faithfulness": 0.95, "completeness": 0.9, "guardrail_compliance": 1.0, "label": "grounded", "reasoning": "great"}')
    agent = EvaluatorAgent(model=model, config=NO_TRACE)
    _, events = agent.run("query", _GOOD_RESEARCH)

    guard_events = [e for e in events if e["event_type"] == "guard_triggered"]
    assert guard_events == []


def test_evaluator_clamps_scores_to_0_1():
    model = _FakeLLM('{"faithfulness": 1.5, "completeness": -0.3, "guardrail_compliance": 2.0, "label": "grounded", "reasoning": "out of range"}')
    agent = EvaluatorAgent(model=model, config=NO_TRACE)
    result, _ = agent.run("query", _GOOD_RESEARCH)

    assert result["faithfulness"] == 1.0
    assert result["completeness"] == 0.0
    assert result["guardrail_compliance"] == 1.0


def test_evaluator_handles_malformed_json_gracefully():
    """When the LLM returns non-JSON, defaults to 0.5 scores and 'hallucinated' label."""
    model = _FakeLLM("I cannot evaluate this.")
    agent = EvaluatorAgent(model=model, config=NO_TRACE)
    result, _ = agent.run("query", _GOOD_RESEARCH)

    assert result["faithfulness"] == 0.5
    assert result["completeness"] == 0.5
    assert result["guardrail_compliance"] == 0.5
    assert result["label"] == "hallucinated"


def test_evaluator_stores_raw_response():
    raw_json = '{"faithfulness": 0.8, "completeness": 0.7, "guardrail_compliance": 1.0, "label": "grounded", "reasoning": "ok"}'
    model = _FakeLLM(raw_json)
    agent = EvaluatorAgent(model=model, config=NO_TRACE)
    result, _ = agent.run("query", _GOOD_RESEARCH)

    assert result["raw_response"] == raw_json


def test_evaluator_infers_label_from_faithfulness_when_label_missing():
    model = _FakeLLM('{"faithfulness": 0.3, "completeness": 0.5, "guardrail_compliance": 1.0, "reasoning": "no label key"}')
    agent = EvaluatorAgent(model=model, config=NO_TRACE)
    result, _ = agent.run("query", _GOOD_RESEARCH)

    assert result["label"] == "hallucinated"


def test_evaluator_infers_grounded_label_when_label_key_absent_and_faith_high():
    model = _FakeLLM('{"faithfulness": 0.9, "completeness": 0.8, "guardrail_compliance": 1.0, "reasoning": "no label key"}')
    agent = EvaluatorAgent(model=model, config=NO_TRACE)
    result, _ = agent.run("query", _GOOD_RESEARCH)

    assert result["label"] == "grounded"
