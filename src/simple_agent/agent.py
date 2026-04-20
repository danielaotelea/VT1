"""Simple arithmetic agent — single-agent prototype used in Round 1 tool evaluations.

Architecture:
  SimpleAgent wraps a single LangGraph-style ReAct loop:
    call_llm → check tool_calls → call_tool (repeat) → final answer

  Observability is wired through a pluggable exporter selected by AgentConfig.exporter.
  When exporter="none" the agent runs without any tracing, which is the default for tests.

  CostTracker accumulates token usage from each LLM response so total cost can be
  queried after a run without depending on any external platform.
"""

from collections import Counter
from dataclasses import dataclass
from typing import Any, Optional, cast

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.graph import add_messages

from .config import AgentConfig

load_dotenv()


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def add(a: int, b: int) -> int:
    """Adds `a` and `b`.

    Args:
        a: First integer.
        b: Second integer.
    """
    return a + b


@tool
def multiply(a: int, b: int) -> int:
    """Multiplies `a` and `b`.

    Args:
        a: First integer.
        b: Second integer.
    """
    return a * b


@tool
def divide(a: int, b: int) -> float:
    """Divides `a` by `b`.

    Args:
        a: Numerator.
        b: Denominator (must not be zero).
    """
    if b == 0:
        raise ValueError("Cannot divide by zero.")
    return a / b


DEFAULT_TOOLS = [add, multiply, divide]


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------

@dataclass
class CostRecord:
    """A single LLM call's token usage and computed cost."""
    agent_role: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class CostTracker:
    """Accumulates per-call token usage and derives USD cost.

    Usage::

        tracker = CostTracker(config)
        response = model.invoke(messages)
        tracker.record(response)
        print(tracker.total_cost())
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.records: list[CostRecord] = []

    def record(self, response, agent_role: str = "simple_agent") -> None:
        """Parse usage_metadata from a LangChain message and append a CostRecord.

        No-ops silently when the response carries no usage metadata (e.g. fake models
        used in tests).
        """
        usage = getattr(response, "usage_metadata", None)
        if not usage:
            return
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        cost = (
            input_tokens * self.config.input_token_price_per_million / 1_000_000
            + output_tokens * self.config.output_token_price_per_million / 1_000_000
        )
        self.records.append(CostRecord(
            agent_role=agent_role,
            model=self.config.model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        ))

    def total_cost(self) -> float:
        """Total USD cost across all recorded calls."""
        return sum(r.cost_usd for r in self.records)

    def total_tokens(self) -> dict[str, int]:
        """Aggregate input and output token counts."""
        return {
            "input": sum(r.input_tokens for r in self.records),
            "output": sum(r.output_tokens for r in self.records),
        }


# ---------------------------------------------------------------------------
# Guard errors
# ---------------------------------------------------------------------------

class LoopDetectedError(RuntimeError):
    """Raised when the loop-detection guard triggers.

    The same tool being called more than ``AgentConfig.max_identical_tool_calls``
    times within a single session is treated as an infinite loop.
    """


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class SimpleAgent:
    """Single LLM + tools ReAct agent with pluggable observability.

    Keeps the LangGraph message-passing conventions (``add_messages`` reducer,
    ``BaseMessage`` lists) so the same traces are produced whether the agent is
    run standalone or embedded inside a LangGraph graph.
    """

    SYSTEM_PROMPT = (
        "You are a helpful assistant tasked with performing arithmetic. "
        "Use the provided tools to compute the answer."
    )

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

        # bind_tools is called only when the model supports it so that
        # fake/stub models can be injected in tests without it.
        self.model: Any = (
            resolved_model.bind_tools(self.tools)
            if hasattr(resolved_model, "bind_tools")
            else resolved_model
        )

        self._exporter = self._init_exporter()

    # ------------------------------------------------------------------
    # Exporter setup
    # ------------------------------------------------------------------

    def _init_exporter(self):
        """Initialise the tracing backend selected by config.exporter.

        Returns the exporter module/object on success, or None on failure
        (missing API key, import error). The agent always runs; tracing is
        best-effort.
        """
        if self.config.exporter == "langwatch":
            try:
                import langwatch
                langwatch.setup()
                return langwatch
            except Exception:
                return None

        if self.config.exporter == "langfuse":
            try:
                from langfuse.callback import CallbackHandler
                return CallbackHandler()
            except Exception:
                return None

        if self.config.exporter == "phoenix":
            try:
                import phoenix as px
                from openinference.instrumentation.langchain import LangChainInstrumentor
                px.launch_app()
                LangChainInstrumentor().instrument()
                return px
            except Exception:
                return None

        if self.config.exporter == "opik":
            try:
                import opik
                opik.configure(use_local=True)
                from opik.integrations.langchain import OpikTracer
                return OpikTracer()
            except Exception:
                return None

        if self.config.exporter == "otel-stdout":
            try:
                from opentelemetry import trace as otel_trace
                from opentelemetry.sdk.trace import TracerProvider
                from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
                provider = TracerProvider()
                provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
                otel_trace.set_tracer_provider(provider)
                return provider
            except Exception:
                return None

        # "none" requires no setup
        return None

    def _langchain_callback(self):
        """Return a LangChain callback for the active trace, or None.

        - langwatch: obtains the per-trace callback from the active trace context.
        - langfuse: the CallbackHandler stored in _exporter is used directly.
        - opik: the OpikTracer stored in _exporter is used directly.
        - phoenix: auto-instruments via OpenInference; no per-call callback needed.
        """
        if self._exporter is None:
            return None
        if self.config.exporter == "langwatch":
            try:
                return self._exporter.get_current_trace().get_langchain_callback()
            except Exception:
                return None
        if self.config.exporter in ("langfuse", "opik"):
            return self._exporter
        return None

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------

    def _call_llm(self, messages: list[BaseMessage]) -> BaseMessage:
        callback = self._langchain_callback()
        invoke_kwargs: dict = {}
        if callback is not None:
            invoke_kwargs["config"] = RunnableConfig(callbacks=[callback])

        response = self.model.invoke(
            [SystemMessage(content=self.SYSTEM_PROMPT)] + messages,
            **invoke_kwargs,
        )
        self.cost_tracker.record(response)
        return response

    def _call_tool(self, tool_call: dict):
        """Invoke a single tool and return the resulting ToolMessage."""
        tool_fn = self.tools_by_name[tool_call["name"]]
        return tool_fn.invoke(tool_call)

    def invoke(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """Run the ReAct loop to completion and return the full message list.

        Raises:
            LoopDetectedError: When the same tool is called more than
                ``config.max_identical_tool_calls`` times.
        """
        tool_call_counts: Counter = Counter()

        # Optionally wrap the entire run in a LangWatch trace
        def _run():
            nonlocal messages
            model_response = self._call_llm(messages)

            while True:
                tool_calls = getattr(model_response, "tool_calls", None) or []
                if not tool_calls:
                    break

                # Loop-detection guard
                for tc in tool_calls:
                    tool_call_counts[tc["name"]] += 1
                    if tool_call_counts[tc["name"]] > self.config.max_identical_tool_calls:
                        raise LoopDetectedError(
                            f"Tool '{tc['name']}' called "
                            f"{tool_call_counts[tc['name']]} times — "
                            f"limit is {self.config.max_identical_tool_calls}."
                        )

                tool_results = [self._call_tool(tc) for tc in tool_calls]
                messages = cast(list[BaseMessage], add_messages(messages, [model_response, *tool_results]))  # type: ignore
                model_response = self._call_llm(messages)

            return cast(list[BaseMessage], add_messages(messages, model_response))  # type: ignore

        if self.config.exporter == "langwatch" and self._exporter is not None:
            try:
                with self._exporter.trace(name="Arithmetic Agent"):
                    return _run()
            except Exception:
                pass

        return _run()

    def stream(self, messages: list[BaseMessage]):
        """Yield per-message updates (mirrors LangGraph stream_mode='updates')."""
        result = self.invoke(messages)
        for msg in result:
            yield {"messages": [msg]}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def build_agent(
    model=None,
    tools: Optional[list] = None,
    config: Optional[AgentConfig] = None,
) -> SimpleAgent:
    """Factory that returns a configured SimpleAgent.

    All parameters are optional; omitting them produces an agent with sensible
    defaults (GPT-4o, arithmetic tools, LangWatch exporter).

    Pass ``config=AgentConfig(exporter="none")`` in tests to avoid requiring
    any observability API keys.
    """
    return SimpleAgent(model=model, tools=tools, config=config)


def main(prompt: str, agent: Optional[SimpleAgent] = None) -> str:
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
    result = agent.invoke(messages)

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
