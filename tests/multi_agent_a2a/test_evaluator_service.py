"""Tests for EvaluatorExecutor (A2A executor wrapping RagasFaithfulnessEvaluator).

The executor is tested in isolation: a fake async evaluator is injected so
neither RAGAS nor the OpenAI API is called.  Tests verify the A2A wire contract
(task state transitions, artifact shape) not the scoring logic itself.
"""

import types

from a2a.helpers import get_data_parts, new_data_message
from a2a.types import Role, TaskState

from src.multi_agent.state import EvaluationResult, ResearchResult
from src.multi_agent_a2a.evaluator_service import EvaluatorExecutor

_RESEARCH: ResearchResult = {
    "summary": "Langfuse and Phoenix are LLM observability tools.",
    "sources": [{"url": "https://langfuse.com", "excerpt": "Langfuse traces LLM calls."}],
}

_HIGH_SCORE: EvaluationResult = {
    "faithfulness": 0.9,
    "label": "grounded",
    "raw_response": "ragas_faithfulness=0.9000",
    "reason": "",
}


class _FakeEvaluator:
    """Duck-typed fake for FaithfulnessEvaluator with a fixed synchronous run()."""

    def __init__(self, result: EvaluationResult | None = None):
        self._result = result or _HIGH_SCORE

    def run(self, query: str, research: ResearchResult, callback=None):
        return self._result, []


class _CollectingQueue:
    def __init__(self):
        self.events: list = []

    async def enqueue_event(self, event) -> None:
        self.events.append(event)


def _make_context(payload: dict):
    message = new_data_message(data=payload, role=Role.ROLE_USER)
    return types.SimpleNamespace(message=message, current_task=None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_evaluator_executor_returns_completed_task():
    executor = EvaluatorExecutor(_FakeEvaluator())
    queue = _CollectingQueue()
    ctx = _make_context({"query": "AI tools?", "research": _RESEARCH})
    await executor.execute(ctx, queue)

    states = [e.status.state for e in queue.events if hasattr(e, "status")]
    assert TaskState.TASK_STATE_COMPLETED in states


async def test_evaluator_executor_artifact_contains_faithfulness():
    result: EvaluationResult = {
        "faithfulness": 0.85,
        "label": "grounded",
        "raw_response": "ragas_faithfulness=0.8500",
        "reason": "",
    }
    executor = EvaluatorExecutor(_FakeEvaluator(result))
    queue = _CollectingQueue()
    ctx = _make_context({"query": "query", "research": _RESEARCH})
    await executor.execute(ctx, queue)

    artifact_events = [e for e in queue.events if hasattr(e, "artifact")]
    assert len(artifact_events) >= 1
    data = get_data_parts(artifact_events[0].artifact.parts)[0]
    assert data["result"]["faithfulness"] == 0.85
    assert data["result"]["label"] == "grounded"
    assert "trace_events" in data


async def test_evaluator_executor_passes_query_and_research_to_agent():
    calls: list[tuple] = []

    class _TrackingEvaluator:
        def run(self, query: str, research: ResearchResult, callback=None):
            calls.append((query, research))
            return _HIGH_SCORE, []

    executor = EvaluatorExecutor(_TrackingEvaluator())  # type: ignore[arg-type]
    queue = _CollectingQueue()
    ctx = _make_context({"query": "check this", "research": _RESEARCH})
    await executor.execute(ctx, queue)

    assert len(calls) == 1
    assert calls[0][0] == "check this"
    assert calls[0][1]["summary"] == _RESEARCH["summary"]
