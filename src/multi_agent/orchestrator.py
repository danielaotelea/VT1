"""OrchestratorAgent — entry point for the multi-agent Research & Fact-Check system.

Graph structure (LangGraph StateGraph):

    START → research → evaluate ──(faithfulness OK or retries exhausted)──→ synthesise → END
                  ↑──────────────(faithfulness low, retries remaining)────┘

Safety guards (enforced inside graph nodes):
  - loop_detection  (research):   same query > max_identical_tool_calls → LoopDetectedError.
  - pii_exposure    (research):   credential pattern in output → PIIExposureError.
  - low_confidence  (evaluate):   faithfulness < threshold → increment retry_count.
  - hitl_escalation (synthesise): retries exhausted → hitl_required = True.

Observability:
  trace_events uses operator.add so every node appends its own events;
  the full inter-agent audit trail accumulates automatically across the graph.
"""

import logging
import re
from typing import Any, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from .config import MultiAgentConfig
from .evaluator import EvaluatorAgent
from .exporter import ExporterAdapter, build_exporter
from .otel_utils import record_exception as _record_exception
from .otel_utils import set_token_cost_attributes as _set_token_cost_attributes
from .prompts import PROMPTS
from .researcher import ResearcherAgent
from .state import AgentState, EvaluationResult, ResearchResult, TraceEvent, make_event

log = logging.getLogger("multi_agent.orchestrator")

_PII_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|[A-Za-z0-9]{32,}=|password\s*[:=]\s*\S+)",
    re.IGNORECASE,
)

class LoopDetectedError(RuntimeError):
    """Raised when the loop-detection guard triggers."""


class PIIExposureError(RuntimeError):
    """Raised when a credential / PII pattern is found in agent output."""


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------

def _session_id(config: Optional[RunnableConfig]) -> Optional[str]:
    return (config or {}).get("configurable", {}).get("session_id") or None


# ---------------------------------------------------------------------------
# OrchestratorAgent
# ---------------------------------------------------------------------------

class OrchestratorAgent:
    """Coordinates Researcher and Evaluator agents via a LangGraph StateGraph.

    Parameters
    ----------
    researcher, evaluator:
        Agent instances.  Created from *config* when None.
    model:
        LangChain chat model for final-answer synthesis.
        Created from config.orchestrator_model when None.
    config:
        Shared MultiAgentConfig.
    """

    def __init__(
        self,
        researcher: Optional[ResearcherAgent] = None,
        evaluator: Optional[EvaluatorAgent] = None,
        model=None,
        config: Optional[MultiAgentConfig] = None,
    ):
        self.config = config or MultiAgentConfig()
        self.researcher = researcher or ResearcherAgent(config=self.config)
        self.evaluator = evaluator or EvaluatorAgent(config=self.config)
        self._adapter: ExporterAdapter = build_exporter(self.config)
        self._histories: dict[str, list[BaseMessage]] = {}
        self._graph = self._build_graph()

        if model is not None:
            self.model: Any = model
        else:
            self.model = ChatOpenAI(
                model=self.config.orchestrator_model,
                temperature=self.config.temperature,
            )

    @property
    def tracing_active(self) -> bool:
        """True when an observability backend is connected and sending spans."""
        return self._adapter.active

    # ------------------------------------------------------------------
    # Graph
    # ------------------------------------------------------------------

    def _build_graph(self):
        g = StateGraph(AgentState)
        g.add_node("research",   self._research_node)
        g.add_node("evaluate",   self._evaluate_node)
        g.add_node("synthesize", self._synthesize_node)
        g.set_entry_point("research")
        g.add_edge("research", "evaluate")
        g.add_conditional_edges(
            "evaluate",
            self._route_after_evaluation,
            {"research": "research", "synthesize": "synthesize"},
        )
        g.add_edge("synthesize", END)
        return g.compile()

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def _research_node(self, state: AgentState, config: RunnableConfig) -> dict:
        query = state["query"]

        counts = dict(state.get("query_counts") or {})
        counts[query] = counts.get(query, 0) + 1
        if counts[query] > self.config.max_identical_tool_calls:
            exc = LoopDetectedError(
                f"Query submitted {counts[query]} times — "
                f"limit is {self.config.max_identical_tool_calls}."
            )
            _record_exception(exc)
            raise exc

        call_event = make_event("orchestrator","tool_call", {"tool": "ResearcherAgent", "query": query})
        cb = self._adapter.callback(_session_id(config))
        research, r_events = self.researcher.run(
            query,
            callback=cb,
            runnable_config=config if cb is None else None,
        )

        if _PII_PATTERN.search(research.get("summary", "")):
            exc = PIIExposureError("Credential / PII pattern detected in research output.")
            _record_exception(exc)
            raise exc

        return {
            "research":     research,
            "trace_events": [call_event] + r_events,
            "query_counts": counts,
            "messages":     [AIMessage(content=f"[researcher] {research.get('summary', '')}")],
        }

    def _evaluate_node(self, state: AgentState, config: RunnableConfig) -> dict:
        call_event = make_event("orchestrator","tool_call", {"tool": "EvaluatorAgent"})
        cb = self._adapter.callback(_session_id(config))
        evaluation, e_events = self.evaluator.run(
            state["query"], state["research"],
            callback=cb,
            runnable_config=config if cb is None else None,
        )

        faithfulness = evaluation.get("faithfulness", 0.0)
        log.info(f"Evaluation — faithfulness={faithfulness:.2f} label={evaluation.get('label')}")

        updates: dict = {"evaluation": evaluation, "trace_events": [call_event] + e_events}

        if faithfulness < self.config.low_confidence_threshold:
            retry = state.get("retry_count", 0) + 1
            updates["retry_count"] = retry
            updates["trace_events"] += [make_event("orchestrator","guard_triggered", {
                "guard": "low_confidence",
                "faithfulness": faithfulness,
                "retry_count": retry,
            })]

        return updates

    def _synthesize_node(self, state: AgentState, config: RunnableConfig) -> dict:
        faithfulness = state["evaluation"].get("faithfulness", 0.0)
        retry_count  = state.get("retry_count", 0)
        hitl_required = (
            faithfulness < self.config.low_confidence_threshold
            and retry_count > self.config.max_evaluator_retries
        )

        events: list[TraceEvent] = []
        if hitl_required:
            events.append(make_event("orchestrator","guard_triggered", {"guard": "hitl_escalation"}))
            log.warning(f"HITL escalation — faithfulness={faithfulness:.2f} after {retry_count} retries")
        else:
            log.info("Quality acceptable — synthesising final answer")

        cb = self._adapter.callback(_session_id(config))
        final_answer = self._synthesise(
            query=state["query"],
            research=state["research"],
            evaluation=state["evaluation"],
            callback=cb,
            session_id=_session_id(config),
            conversation_history=state.get("conversation_history") or [],
            runnable_config=config if cb is None else None,
        )
        return {
            "final_answer":  final_answer,
            "hitl_required": hitl_required,
            "trace_events":  events,
            "messages":      [AIMessage(content=final_answer)],
        }

    def _route_after_evaluation(self, state: AgentState) -> str:
        faithfulness = state["evaluation"].get("faithfulness", 0.0)
        retry_count  = state.get("retry_count", 0)
        if faithfulness >= self.config.low_confidence_threshold:
            return "synthesize"
        if retry_count > self.config.max_evaluator_retries:
            return "synthesize"
        return "research"

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def _synthesise(
        self,
        query: str,
        research: ResearchResult,
        evaluation: EvaluationResult,
        callback=None,
        session_id: Optional[str] = None,
        conversation_history: Optional[list[BaseMessage]] = None,
        runnable_config=None,
    ) -> str:
        sources_text = "\n".join(
            f"[{i+1}] {s.get('url', '')} — {s.get('excerpt', '')}"
            for i, s in enumerate(research.get("sources", []))
        )
        user_msg = HumanMessage(content=(
            f"User query: {query}\n\n"
            f"Research summary: {research.get('summary', '')}\n\n"
            f"Sources:\n{sources_text}\n\n"
            f"Faithfulness score: {evaluation.get('faithfulness', 0.0):.2f}"
        ))
        messages: list[BaseMessage] = [
            SystemMessage(content=PROMPTS.orchestrator_synthesis),
            *(conversation_history or []),
            user_msg,
        ]

        if callback is not None:
            invoke_config = RunnableConfig(callbacks=[callback])
        elif runnable_config is not None:
            invoke_config = runnable_config
        else:
            invoke_config = None

        response = self.model.invoke(
            messages,
            **({"config": invoke_config} if invoke_config else {}),
        )
        usage = getattr(response, "usage_metadata", None)
        if usage:
            inp, out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
            cost = (inp * self.config.input_token_price_per_million
                    + out * self.config.output_token_price_per_million) / 1_000_000
            _set_token_cost_attributes(inp, out, cost)

        answer = getattr(response, "content", str(response))
        sources = [s for s in research.get("sources", []) if s.get("url")]
        if sources:
            sources_block = "\n".join(
                f"[{i+1}] {s['url']}" for i, s in enumerate(sources)
            )
            answer = f"{answer}\n\n**Sources:**\n{sources_block}"
        return answer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        query: str,
        session_id: Optional[str] = None,
        conversation_history: Optional[list[BaseMessage]] = None,
    ) -> AgentState:
        """Research *query* via the StateGraph and return the final AgentState.

        Raises LoopDetectedError or PIIExposureError when a safety guard fires.
        Pass *conversation_history* (or use run_turn) for multi-turn context.
        """
        log.info(f"Starting run — query: {query[:120]!r} session={session_id}")

        initial_state: AgentState = {
            "query":                query,
            "messages":             [HumanMessage(content=query)],
            "trace_events":         [],
            "research":             {"summary": "", "sources": []},
            "evaluation":           {
                "faithfulness": 0.0, "label": "hallucinated", "raw_response": "", "reason": "",
            },
            "retry_count":          0,
            "hitl_required":        False,
            "final_answer":         "",
            "query_counts":         {},
            "conversation_history": list(conversation_history or []),
        }

        self._adapter._emit_log("orchestrator", session_id)
        run_config = RunnableConfig(
            configurable={
                "session_id": session_id or "",
            },
        )
        with self._adapter.session_ctx(session_id):
            return self._graph.invoke(initial_state, config=run_config)

    def run_turn(self, query: str, session_id: str) -> AgentState:
        """Multi-turn entry point: injects prior Q&A as synthesis context.

        History accumulates per session_id until reset_history() is called.
        The same session_id must be used across turns of one conversation.
        """
        history = self._histories.get(session_id, [])
        state   = self.run(query, session_id=session_id, conversation_history=history)

        turn = self._histories.setdefault(session_id, [])
        turn.append(HumanMessage(content=query))
        turn.append(AIMessage(content=state["final_answer"]))
        return state

    def reset_history(self, session_id: str) -> None:
        """Discard the conversation history for *session_id*."""
        self._histories.pop(session_id, None)


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------

def run(query: str, config: Optional[MultiAgentConfig] = None) -> str:
    """Run the full pipeline and return the final answer string."""
    return OrchestratorAgent(config=config or MultiAgentConfig()).run(query)["final_answer"]
