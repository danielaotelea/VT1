"""Simple arithmetic agent — single-agent prototype used in Round 1 tool evaluations.

Architecture:
  SimpleAgent wraps a single LangGraph-style ReAct loop:
    call_llm → check tool_calls → call_tool (repeat) → final answer

  Observability is wired through a pluggable exporter selected by AgentConfig.exporter.
  When exporter="none" the agent runs without any tracing, which is the default for tests.
"""

import logging
from collections import Counter
from typing import Any, Optional, cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import add_messages

from src.otel_utils import record_exception as _record_exception

from .config import AgentConfig
from .cost import CostTracker
from .exporter import ExporterAdapter, build_exporter
from .prompts import PROMPTS
from .tools import DEFAULT_TOOLS

log = logging.getLogger("simple_agent.agent")


class LoopDetectedError(RuntimeError):
    """Raised when the same tool is called more than ``AgentConfig.max_identical_tool_calls`` times."""

class SimpleAgent:
    """Single LLM + tools ReAct agent with pluggable observability.

    Keeps the LangGraph message-passing conventions (``add_messages`` reducer,
    ``BaseMessage`` lists) so the same traces are produced whether the agent is
    run standalone or embedded inside a LangGraph graph.
    """

    SYSTEM_PROMPT = PROMPTS.system

    def __init__(
        self,
        model=None,
        tools: Optional[list[Any]] = None,
        config: Optional[AgentConfig] = None,
    ):
        self.config = config or AgentConfig()
        self.tools: list[Any] = tools if tools is not None else DEFAULT_TOOLS
        self.tools_by_name: dict[str, Any] = {t.name: t for t in self.tools}
        self.cost_tracker = CostTracker(self.config)

        resolved_model: Any = (
            model if model is not None
            else ChatOpenAI(model=self.config.model_name, temperature=self.config.temperature)
        )

        # bind_tools only when the model supports it so fake models can be injected in tests.
        self.model: Any = (
            resolved_model.bind_tools(self.tools)
            if hasattr(resolved_model, "bind_tools")
            else resolved_model
        )

        self._adapter: ExporterAdapter = build_exporter(self.config)

    @property
    def tracing_active(self) -> bool:
        """True when an observability backend is connected and sending spans."""
        return self._adapter.active

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------

    def _call_llm(self, messages: list[BaseMessage], session_id: Optional[str] = None) -> BaseMessage:
        log.info(f"LLM call — {len(messages) + 1} message(s) in context")
        callback = self._adapter.callback(session_id=session_id)
        invoke_kwargs: dict = {}
        if callback is not None:
            invoke_kwargs["config"] = RunnableConfig(callbacks=[callback])

        response = self.model.invoke(
            [SystemMessage(content=self.SYSTEM_PROMPT)] + messages,
            **invoke_kwargs,
        )  # type: ignore[call-overload]
        self.cost_tracker.record(response)

        tool_calls = getattr(response, "tool_calls", []) or []
        if tool_calls:
            log.info(f"LLM requested tool calls: {[tc['name'] for tc in tool_calls]}")
        else:
            log.info(f"LLM final answer: {getattr(response, 'content', '')[:120]!r}")
        return response

    def _call_tool(self, tool_call: dict):
        """Invoke a single tool and return the resulting ToolMessage."""
        log.info(f"Tool call: {tool_call['name']}({tool_call.get('args', {})})")
        tool_fn = self.tools_by_name[tool_call["name"]]
        result = tool_fn.invoke(tool_call)
        log.info(f"Tool result: {getattr(result, 'content', result)}")
        return result

    def invoke(self, messages: list[BaseMessage], session_id: Optional[str] = None) -> list[BaseMessage]:
        """Run the ReAct loop to completion and return the full message list.

        Raises:
            LoopDetectedError: When the same tool is called more than
                ``config.max_identical_tool_calls`` times.
        """
        tool_call_counts: Counter = Counter()

        def _run():
            nonlocal messages
            model_response = self._call_llm(messages, session_id=session_id)

            while True:
                tool_calls = getattr(model_response, "tool_calls", None) or []
                if not tool_calls:
                    break

                for tc in tool_calls:
                    tool_call_counts[tc["name"]] += 1
                    if tool_call_counts[tc["name"]] > self.config.max_identical_tool_calls:
                        exc = LoopDetectedError(
                            f"Tool '{tc['name']}' called "
                            f"{tool_call_counts[tc['name']]} times — "
                            f"limit is {self.config.max_identical_tool_calls}."
                        )
                        _record_exception(exc)
                        raise exc

                tool_results = [self._call_tool(tc) for tc in tool_calls]
                messages = cast(list[BaseMessage], add_messages(messages, [model_response, *tool_results]))  # type: ignore
                model_response = self._call_llm(messages, session_id=session_id)

            return cast(list[BaseMessage], add_messages(messages, model_response))  # type: ignore

        self._adapter._emit_log("simple_agent", session_id)
        with self._adapter.trace_ctx("Arithmetic Agent"):
            with self._adapter.session_ctx(session_id):
                return _run()

    def stream(self, messages: list[BaseMessage]):
        """Yield per-message updates (mirrors LangGraph stream_mode='updates')."""
        for msg in self.invoke(messages):
            yield {"messages": [msg]}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def build_agent(
    model=None,
    tools: Optional[list] = None,
    config: Optional[AgentConfig] = None,
) -> SimpleAgent:
    """Return a configured SimpleAgent.

    All parameters are optional; defaults are GPT-4o, arithmetic tools, no tracing.
    Pass an explicit ``config`` to enable an observability backend or tune behaviour.
    """
    return SimpleAgent(model=model, tools=tools, config=config)


def main(prompt: str, agent: Optional[SimpleAgent] = None, session_id: Optional[str] = None) -> str:
    """Run the agent on *prompt* and return a human-readable trace string.

    The string includes every message in the final message list so callers can
    inspect which tools were called and what the final answer was::

        [human] Add 13 and 37.
        [tool:add({'a': 13, 'b': 37})]
        [tool] 50
        [ai] The answer is 50.
    """
    if agent is None:
        agent = build_agent()

    messages: list[BaseMessage] = cast(list[BaseMessage], [HumanMessage(content=prompt)])
    result = agent.invoke(messages, session_id=session_id)

    parts: list[str] = []
    for msg in result:
        role = type(msg).__name__.replace("Message", "").lower()
        content = getattr(msg, "content", "") or ""
        tool_calls = getattr(msg, "tool_calls", []) or []

        for tc in tool_calls:
            parts.append(f"[tool:{tc['name']}({tc.get('args', {})})]")

        if content:
            parts.append(f"[{role}] {content}")

    return "\n".join(parts)
