"""OrchestratorAgent (A2A v2) — drives Researcher and Evaluator over the network.

Architecture:

    User query
        │
        ▼
    OrchestratorAgentA2A  (this process, port 8002)
        │  A2A JSON-RPC call
        ├──► Researcher Agent service  (port 8011)
        │         └── ResearcherAgent.run(query) → ResearchResult
        │  A2A JSON-RPC call
        └──► Evaluator Agent service   (port 8012)
                  └── EvaluatorAgent.run(query, research) → EvaluationResult

The orchestration logic is a plain async while-loop (research → evaluate →
retry-or-synthesise).  LangGraph was removed: the graph added no value here
(sequential flow + single conditional retry) but introduced LangChain callback
instrumentation that clashed with the manual OTel spans and produced a noisy
trace with misplaced span nesting.
"""

import logging
import re
from typing import Any, Callable, Coroutine, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from src.multi_agent.otel_utils import record_exception as _record_exception
from src.multi_agent.otel_utils import set_token_cost_attributes as _set_token_cost_attributes
from src.otel_utils import current_trace_id as _current_trace_id
from src.multi_agent.prompts import PROMPTS
from src.multi_agent.state import EvaluationResult, ResearchResult, TraceEvent, make_event
from src.multi_agent_a2a.tracing import TracingStrategy, build_tracing
from .config import MultiAgentA2AConfig
from .protocol import call_agent as _default_call_agent

log = logging.getLogger("multi_agent_a2a.orchestrator")

_PII_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|[A-Za-z0-9]{32,}=|password\s*[:=]\s*\S+)",
    re.IGNORECASE,
)


class LoopDetectedError(RuntimeError):
    """Raised when the loop-detection guard triggers."""


class PIIExposureError(RuntimeError):
    """Raised when a credential / PII pattern is found in agent output."""


# ---------------------------------------------------------------------------
# OrchestratorAgentA2A
# ---------------------------------------------------------------------------

class OrchestratorAgentA2A:
    """Coordinates Researcher and Evaluator agents via A2A JSON-RPC calls.

    Parameters
    ----------
    model:
        LangChain chat model for final-answer synthesis.
    config:
        MultiAgentA2AConfig with URLs / thresholds.
    call_agent_fn:
        Injectable async function ``(url, payload, headers) -> (result, events)``.
        Defaults to :func:`protocol.call_agent`.  Override in tests to avoid
        real network calls.
    """

    def __init__(
        self,
        model=None,
        config: Optional[MultiAgentA2AConfig] = None,
        call_agent_fn: Optional[Callable[..., Coroutine]] = None,
    ):
        self.config = config or MultiAgentA2AConfig()
        self._call_agent = call_agent_fn or _default_call_agent
        self._strategy: TracingStrategy = build_tracing(
            self.config.exporter,
            service_name="orchestrator",
        )
        self._histories: dict[str, list[BaseMessage]] = {}

        if model is not None:
            self.model: Any = model
        else:
            self.model = ChatOpenAI(
                model=self.config.orchestrator_model,
                temperature=self.config.temperature,
            )

    @property
    def tracing_active(self) -> bool:
        return self._strategy.active

    # ------------------------------------------------------------------
    # Internal async steps
    # ------------------------------------------------------------------

    async def _do_research(
        self,
        query: str,
        session_id: Optional[str],
    ) -> tuple[ResearchResult, list[TraceEvent]]:
        log.info(f"[orchestrator] trace_id={_current_trace_id()} calling ResearcherAgent session={session_id}")
        headers = self._strategy.outgoing_headers(session_id=session_id)
        research, events = await self._call_agent(
            self.config.researcher_url, {"query": query}, headers=headers
        )
        if _PII_PATTERN.search(research.get("summary", "")):
            exc = PIIExposureError("Credential / PII pattern detected in research output.")
            _record_exception(exc)
            raise exc
        return research, events

    async def _do_evaluate(
        self,
        query: str,
        research: ResearchResult,
        session_id: Optional[str],
    ) -> tuple[EvaluationResult, list[TraceEvent]]:
        log.info(f"[orchestrator] trace_id={_current_trace_id()} calling EvaluatorAgent session={session_id}")
        headers = self._strategy.outgoing_headers(session_id=session_id)
        evaluation, events = await self._call_agent(
            self.config.evaluator_url,
            {"query": query, "research": research},
            headers=headers,
        )
        faithfulness = evaluation.get("faithfulness", 0.0)
        log.info(f"Evaluation — faithfulness={faithfulness:.2f} label={evaluation.get('label')}")
        return evaluation, events

    # ------------------------------------------------------------------
    # Synthesis (runs in the Orchestrator process, uses self.model)
    # ------------------------------------------------------------------

    def _synthesise(
        self,
        query: str,
        research: ResearchResult,
        evaluation: EvaluationResult,
        callback=None,
        session_id: Optional[str] = None,
        conversation_history: Optional[list[BaseMessage]] = None,
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

        invoke_kwargs: dict = {}
        if callback is not None:
            invoke_kwargs["config"] = RunnableConfig(callbacks=[callback])

        response = self.model.invoke(messages, **invoke_kwargs)
        usage = getattr(response, "usage_metadata", None)
        if usage:
            inp, out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
            cost = (
                inp * self.config.input_token_price_per_million
                + out * self.config.output_token_price_per_million
            ) / 1_000_000
            _set_token_cost_attributes(inp, out, cost)

        answer = getattr(response, "content", str(response))
        sources = [s for s in research.get("sources", []) if s.get("url")]
        if sources:
            answer = f"{answer}\n\n**Sources:**\n" + "\n".join(
                f"[{i+1}] {s['url']}" for i, s in enumerate(sources)
            )
        return answer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        query: str,
        session_id: Optional[str] = None,
        conversation_history: Optional[list[BaseMessage]] = None,
    ) -> dict:
        """Research *query* and return a result dict compatible with AgentState."""
        log.info(f"Starting run — query: {query[:120]!r} session={session_id}")

        async def _pipeline():
            trace_events: list[TraceEvent] = []
            retry_count:  int = 0
            query_counts: dict[str, int] = {}

            research: ResearchResult = {"summary": "", "sources": []}
            evaluation: EvaluationResult = {
                "faithfulness": 0.0, "label": "hallucinated", "raw_response": "", "reason": "",
            }

            # ── Research → Evaluate loop ──────────────────────────────
            while True:
                # Loop-detection guard
                query_counts[query] = query_counts.get(query, 0) + 1
                if query_counts[query] > self.config.max_identical_tool_calls:
                    exc = LoopDetectedError(
                        f"Query submitted {query_counts[query]} times — "
                        f"limit is {self.config.max_identical_tool_calls}."
                    )
                    _record_exception(exc)
                    raise exc

                call_event = make_event("orchestrator", "tool_call", {
                    "tool": "ResearcherAgent (A2A)", "query": query,
                })
                research, r_events = await self._do_research(query, session_id)
                trace_events.extend([call_event] + r_events)

                call_event = make_event("orchestrator", "tool_call", {
                    "tool": "EvaluatorAgent (A2A)",
                })
                evaluation, e_events = await self._do_evaluate(query, research, session_id)
                trace_events.extend([call_event] + e_events)

                faithfulness = evaluation.get("faithfulness", 0.0)

                if faithfulness >= self.config.low_confidence_threshold:
                    break

                retry_count += 1
                trace_events.append(make_event("orchestrator", "guard_triggered", {
                    "guard": "low_confidence",
                    "faithfulness": faithfulness,
                    "retry_count": retry_count,
                }))

                if retry_count > self.config.max_evaluator_retries:
                    break

            # ── Synthesise ────────────────────────────────────────────
            faithfulness = evaluation.get("faithfulness", 0.0)
            hitl_required = (
                faithfulness < self.config.low_confidence_threshold
                and retry_count > self.config.max_evaluator_retries
            )

            if hitl_required:
                trace_events.append(make_event("orchestrator", "guard_triggered", {
                    "guard": "hitl_escalation",
                }))
                log.warning(
                    f"HITL escalation — faithfulness={faithfulness:.2f} "
                    f"after {retry_count} retries"
                )
            else:
                log.info("Quality acceptable — synthesising final answer")

            callback    = self._strategy.get_callback(session_id=session_id)
            final_answer = self._synthesise(
                query=query,
                research=research,
                evaluation=evaluation,
                callback=callback,
                session_id=session_id,
                conversation_history=list(conversation_history or []),
            )

            return {
                "query":                query,
                "messages":             [HumanMessage(content=query), AIMessage(content=final_answer)],
                "trace_events":         trace_events,
                "research":             research,
                "evaluation":           evaluation,
                "retry_count":          retry_count,
                "hitl_required":        hitl_required,
                "final_answer":         final_answer,
                "query_counts":         query_counts,
                "conversation_history": list(conversation_history or []),
            }

        return await self._strategy.wrap_run(_pipeline, session_id=session_id)()

    async def run_turn(self, query: str, session_id: str) -> dict:
        """Multi-turn entry point: injects prior Q&A as synthesis context."""
        history = self._histories.get(session_id, [])
        state   = await self.run(query, session_id=session_id, conversation_history=history)

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

async def run(query: str, config: Optional[MultiAgentA2AConfig] = None) -> str:
    """Run the full A2A pipeline and return the final answer string."""
    return (await OrchestratorAgentA2A(config=config or MultiAgentA2AConfig()).run(query))["final_answer"]
