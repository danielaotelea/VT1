"""Tests for src/simple_agent/agent.py.

All tests inject a fake model so that no OpenAI API key or observability
platform is required. Observability is disabled via AgentConfig(exporter="none").
"""

from typing import Any, cast

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from src.simple_agent.agent import (
    CostTracker,
    LoopDetectedError,
    SimpleAgent,
    add,
    build_agent,
    divide,
    main,
    multiply,
)
from src.simple_agent.config import AgentConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NO_TRACE = AgentConfig(exporter="none")


class _SingleToolCallModel:
    """Returns one tool call on first invoke, then a plain answer."""

    def __init__(self, tool_name: str, args: dict, final: str = "Done."):
        self._tool_name = tool_name
        self._args = args
        self._final = final
        self._calls = 0

    def invoke(self, messages: list, **kwargs) -> AIMessage:
        self._calls += 1
        if self._calls == 1:
            return AIMessage(
                content="",
                tool_calls=[{"name": self._tool_name, "id": "t1", "args": self._args}],
            )
        return AIMessage(content=self._final)


class _DirectAnswerModel:
    """Always returns a plain answer with no tool calls."""

    def invoke(self, messages: list, **kwargs) -> AIMessage:
        return AIMessage(content="The answer is 42.")


class _AlwaysLoopModel:
    """Always requests the same tool call — triggers the loop guard."""

    def invoke(self, messages: list, **kwargs) -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[{"name": "add", "id": "t1", "args": {"a": 1, "b": 2}}],
        )


class _ModelWithUsage:
    """Returns a response that carries usage_metadata for cost tracking tests."""

    def invoke(self, messages: list, **_kwargs) -> AIMessage:
        msg = AIMessage(content="Done.")
        msg.usage_metadata = cast(Any, {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150})
        return msg


# ---------------------------------------------------------------------------
# Unit tests — individual tools
# ---------------------------------------------------------------------------

def test_add_returns_correct_sum():
    # Direct-args format returns the raw tool output (int)
    result = add.invoke({"a": 3, "b": 4})
    assert result == 7


def test_multiply_returns_correct_product():
    result = multiply.invoke({"a": 6, "b": 7})
    assert result == 42


def test_divide_returns_correct_quotient():
    result = divide.invoke({"a": 10, "b": 4})
    assert result == 2.5


def test_divide_by_zero_raises():
    with pytest.raises(Exception):
        divide.invoke({"a": 5, "b": 0})


def test_tools_return_tool_message_with_agent_format():
    """Tool-call dict with 'type':'tool_call' (as produced by AIMessage) returns ToolMessage."""
    result = add.invoke({"name": "add", "id": "t1", "args": {"a": 3, "b": 4}, "type": "tool_call"})
    assert isinstance(result, ToolMessage)
    assert result.content == "7"
    assert result.tool_call_id == "t1"


# ---------------------------------------------------------------------------
# Agent — happy paths
# ---------------------------------------------------------------------------

def test_agent_single_tool_call_produces_result():
    """Agent calls add(13, 37), gets 50 in a ToolMessage, then returns final answer."""
    model = _SingleToolCallModel("add", {"a": 13, "b": 37}, final="The answer is 50.")
    agent = build_agent(model=model, config=NO_TRACE)

    messages: list[BaseMessage] = [HumanMessage(content="What is 13 + 37?")]
    result = agent.invoke(messages)

    contents = [m.content for m in result if m.content]
    assert any("50" in c for c in contents), f"Expected '50' in output, got: {contents}"


def test_agent_direct_answer_skips_tools():
    """When the model returns no tool calls, the agent exits after one LLM call."""
    model = _DirectAnswerModel()
    agent = build_agent(model=model, config=NO_TRACE)

    messages: list[BaseMessage] = [HumanMessage(content="Tell me something.")]
    result = agent.invoke(messages)

    final = result[-1]
    assert isinstance(final, AIMessage)
    assert final.content == "The answer is 42."


def test_agent_result_includes_original_human_message():
    model = _DirectAnswerModel()
    agent = build_agent(model=model, config=NO_TRACE)

    messages: list[BaseMessage] = [HumanMessage(content="Hello")]
    result = agent.invoke(messages)

    assert result[0].content == "Hello"


# ---------------------------------------------------------------------------
# Agent — edge cases
# ---------------------------------------------------------------------------

def test_loop_detection_raises_after_max_calls():
    """LoopDetectedError is raised when the same tool is called beyond the limit."""
    config = AgentConfig(exporter="none", max_identical_tool_calls=2)
    agent = build_agent(model=_AlwaysLoopModel(), config=config)

    messages: list[BaseMessage] = [HumanMessage(content="Loop me.")]
    with pytest.raises(LoopDetectedError):
        agent.invoke(messages)


def test_loop_detection_limit_is_respected():
    """Tool may be called exactly max_identical_tool_calls times without error."""
    # A model that requests add exactly twice, then stops
    class _TwiceModel:
        def __init__(self):
            self._calls = 0

        def invoke(self, messages: list, **kwargs) -> AIMessage:
            self._calls += 1
            if self._calls <= 2:
                return AIMessage(
                    content="",
                    tool_calls=[{"name": "add", "id": "t1", "args": {"a": 1, "b": 2}}],
                )
            return AIMessage(content="Done after two calls.")

    config = AgentConfig(exporter="none", max_identical_tool_calls=2)
    agent = build_agent(model=_TwiceModel(), config=config)

    messages: list[BaseMessage] = [HumanMessage(content="Add twice.")]
    result = agent.invoke(messages)  # must NOT raise
    assert result[-1].content == "Done after two calls."


def test_empty_tool_calls_list_exits_loop():
    """A response with an empty tool_calls list is treated as a final answer."""
    class _EmptyToolCallsModel:
        def invoke(self, messages: list, **kwargs) -> AIMessage:
            # Return AIMessage with explicitly empty tool_calls
            return AIMessage(content="No tools needed.", tool_calls=[])

    agent = build_agent(model=_EmptyToolCallsModel(), config=NO_TRACE)
    messages: list[BaseMessage] = [HumanMessage(content="Do nothing.")]
    result = agent.invoke(messages)
    assert result[-1].content == "No tools needed."


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------

def test_cost_tracker_records_usage_metadata():
    config = AgentConfig(
        exporter="none",
        input_token_price_per_million=5.0,
        output_token_price_per_million=15.0,
    )
    tracker = CostTracker(config)
    msg = AIMessage(content="done")
    msg.usage_metadata = cast(Any, {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "total_tokens": 2_000_000})
    tracker.record(msg)

    assert len(tracker.records) == 1
    assert tracker.total_cost() == pytest.approx(20.0)  # 5 + 15


def test_cost_tracker_silently_skips_missing_metadata():
    tracker = CostTracker(AgentConfig(exporter="none"))
    msg = AIMessage(content="no usage here")
    tracker.record(msg)  # must not raise

    assert len(tracker.records) == 0
    assert tracker.total_cost() == 0.0


def test_cost_tracker_accumulates_across_multiple_calls():
    config = AgentConfig(
        exporter="none",
        input_token_price_per_million=10.0,
        output_token_price_per_million=10.0,
    )
    tracker = CostTracker(config)
    for _ in range(3):
        msg = AIMessage(content="x")
        msg.usage_metadata = cast(Any, {"input_tokens": 100_000, "output_tokens": 100_000, "total_tokens": 200_000})
        tracker.record(msg)

    assert len(tracker.records) == 3
    assert tracker.total_tokens() == {"input": 300_000, "output": 300_000}
    assert tracker.total_cost() == pytest.approx(6.0)  # 3 * (1.0 input + 1.0 output)


def test_agent_cost_tracker_populated_when_usage_present():
    """Agent's own CostTracker picks up usage from a model that emits metadata."""
    agent = build_agent(model=_ModelWithUsage(), config=NO_TRACE)
    messages: list[BaseMessage] = [HumanMessage(content="Anything.")]
    agent.invoke(messages)

    assert len(agent.cost_tracker.records) == 1
    assert agent.cost_tracker.total_cost() > 0


# ---------------------------------------------------------------------------
# main() helper
# ---------------------------------------------------------------------------

def test_main_returns_non_empty_string():
    agent = build_agent(model=_DirectAnswerModel(), config=NO_TRACE)
    out = main("Say something.", agent=agent)
    assert isinstance(out, str)
    assert len(out) > 0


def test_main_includes_tool_call_and_result():
    """main() output must contain '[tool:add' and '50' when add(13, 37) is called."""
    model = _SingleToolCallModel("add", {"a": 13, "b": 37})
    agent = build_agent(model=model, config=NO_TRACE)
    out = main("Add 13 and 37.", agent=agent)

    assert "[tool:add" in out
    assert "50" in out


def test_main_without_explicit_agent_uses_default_config(monkeypatch):
    """Calling main() without an agent creates one with the default config.

    We monkeypatch build_agent to inject a fake model so no API key is needed.
    """
    import src.simple_agent.agent as agent_module

    captured = []

    def _fake_build(model=None, tools=None, config=None):
        a = SimpleAgent(model=_DirectAnswerModel(), tools=tools, config=AgentConfig(exporter="none"))
        captured.append(a)
        return a

    monkeypatch.setattr(agent_module, "build_agent", _fake_build)
    out = agent_module.main("Hello.")

    assert len(captured) == 1
    assert isinstance(out, str)
