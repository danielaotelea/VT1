"""OrchestratorAgent — entry point for the multi-agent Research & Fact-Check system.

Responsibilities:
  1. Accept a user research query.
  2. Dispatch to ResearcherAgent to gather evidence.
  3. Dispatch to EvaluatorAgent to score the research output.
  4. Retry (up to max_evaluator_retries) when faithfulness < low_confidence_threshold.
  5. Escalate to HITL when retries are exhausted.
  6. Synthesise the final answer and return it.

Safety guards enforced here:
  - loop_detection: same researcher query submitted > max_identical_tool_calls → abort.
  - token_explosion: context > 2× initial size → warn + truncate oldest messages.
  - pii_exposure: API key / credential pattern in research output → block + event.
  - low_confidence: faithfulness < low_confidence_threshold after retries → HITL flag.

Observability:
  The Orchestrator wraps the full run in a LangWatch trace (when exporter="langwatch")
  and appends all TraceEvents from sub-agents to AgentState.trace_events so the
  full inter-agent trace is available to the observability platform.
"""

import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from .config import MultiAgentConfig
from .evaluator import EvaluatorAgent
from .researcher import ResearcherAgent
from .state import AgentState, EvaluationResult, ResearchResult, TraceEvent

load_dotenv()

log = logging.getLogger("multi_agent.orchestrator")


# Matches common credential / API key patterns in text
_PII_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9]{20,}|[A-Za-z0-9]{32,}=|password\s*[:=]\s*\S+)",
    re.IGNORECASE,
)

# Synthesiser system prompt
_SYNTHESIS_PROMPT = (
    "You are a research assistant. Given the research summary and evaluation scores "
    "below, write a clear, concise final answer for the user. Cite sources inline "
    "using [1], [2], … notation matching the sources list."
)


class LoopDetectedError(RuntimeError):
    """Raised when the loop-detection guard triggers."""


class PIIExposureError(RuntimeError):
    """Raised when a credential / PII pattern is found in agent output."""


class OrchestratorAgent:
    """Coordinates Researcher and Evaluator agents to answer a research query.

    Parameters
    ----------
    researcher:
        A :class:`ResearcherAgent` instance.  If None, one is created from *config*.
    evaluator:
        An :class:`EvaluatorAgent` instance.  If None, one is created from *config*.
    model:
        LangChain chat model used by the Orchestrator itself for synthesis.
        If None, a ``ChatOpenAI`` instance is created from ``config.orchestrator_model``.
    config:
        Shared ``MultiAgentConfig``.
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

        if model is not None:
            self.model: Any = model
        else:
            from langchain_openai import ChatOpenAI
            self.model = ChatOpenAI(
                model=self.config.orchestrator_model,
                temperature=self.config.temperature,
            )

        self._exporter = self._init_exporter()

    # ------------------------------------------------------------------
    # Exporter
    # ------------------------------------------------------------------

    def _init_exporter(self):
        if self.config.exporter == "langwatch":
            try:
                import langwatch
                langwatch.setup()
                log.info("Exporter: langwatch initialised")
                return langwatch
            except Exception as e:
                log.warning("Exporter: langwatch failed: %s", e)
                return None
        if self.config.exporter == "langfuse":
            try:
                from langfuse.langchain import CallbackHandler
                handler = CallbackHandler()
                log.info("Exporter: langfuse initialised (url=%s)", os.getenv("LANGFUSE_HOST", "http://localhost:3000"))
                return handler
            except Exception as e:
                log.warning("Exporter: langfuse failed: %s", e)
                return None
        if self.config.exporter == "phoenix":
            try:
                from phoenix.otel import register
                from openinference.instrumentation.langchain import LangChainInstrumentor
                base = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
                endpoint = f"{base.rstrip('/')}/v1/traces"
                tracer_provider = register(project_name="vt1-multi-agent", endpoint=endpoint)
                LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
                log.info("Exporter: phoenix initialised (endpoint=%s)", endpoint)
                return tracer_provider
            except Exception as e:
                log.warning("Exporter: phoenix failed: %s", e)
                return None
        if self.config.exporter == "opik":
            try:
                from opik.integrations.langchain import OpikTracer
                project = os.getenv("OPIK_PROJECT_NAME", "vt1-multi-agent")
                url = os.getenv("OPIK_URL_OVERRIDE", "http://localhost:5173/api")
                tracer = OpikTracer(project_name=project)
                log.info("Exporter: opik initialised (project=%s, url=%s)", project, url)
                return tracer
            except Exception as e:
                log.warning("Exporter: opik failed: %s", e)
                return None
        if self.config.exporter == "otel-stdout":
            try:
                from opentelemetry import trace as otel_trace
                from opentelemetry.sdk.trace import TracerProvider
                from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
                provider = TracerProvider()
                provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
                otel_trace.set_tracer_provider(provider)
                log.info("Exporter: otel-stdout initialised")
                return provider
            except Exception as e:
                log.warning("Exporter: otel-stdout failed: %s", e)
                return None
        log.info("Exporter: none (tracing disabled)")
        return None

    def _langchain_callback(self):
        """Return a LangChain callback for the active exporter, or None.

        Mirrors the same helper in SimpleAgent so the same callback is passed
        to every model.invoke() call — including those inside sub-agents.
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
        # phoenix / otel-stdout: auto-instrumented globally; no per-call callback needed
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ts(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _event(self, event_type: str, payload: dict) -> TraceEvent:
        return TraceEvent(
            timestamp=self._ts(),
            agent="orchestrator",
            event_type=event_type,
            payload=payload,
        )

    def _check_pii(self, text: str, events: list[TraceEvent]) -> None:
        """Raise PIIExposureError and append an event if a credential pattern is found."""
        if _PII_PATTERN.search(text):
            events.append(self._event("guard_triggered", {"guard": "pii_detected"}))
            raise PIIExposureError("Credential / PII pattern detected in research output.")

    def _check_token_explosion(
        self,
        messages: list[BaseMessage],
        initial_size: int,
        events: list[TraceEvent],
    ) -> list[BaseMessage]:
        """Warn and truncate if context grew > 2× the initial message count."""
        if len(messages) > 2 * max(initial_size, 1):
            events.append(self._event("guard_triggered", {
                "guard": "token_explosion",
                "message_count": len(messages),
                "initial_size": initial_size,
            }))
            # Keep the first message (user query) + most recent half
            keep = max(1, len(messages) // 2)
            messages = [messages[0]] + messages[-keep:]
        return messages

    def _synthesise(
        self,
        query: str,
        research: ResearchResult,
        evaluation: EvaluationResult,
        callback=None,
    ) -> str:
        """Call the Orchestrator LLM to produce the final answer."""
        sources_text = "\n".join(
            f"[{i+1}] {s.get('url', '')} — {s.get('excerpt', '')}"
            for i, s in enumerate(research.get("sources", []))
        )
        user_content = (
            f"User query: {query}\n\n"
            f"Research summary: {research.get('summary', '')}\n\n"
            f"Sources:\n{sources_text}\n\n"
            f"Evaluation — faithfulness: {evaluation.get('faithfulness'):.2f}, "
            f"completeness: {evaluation.get('completeness'):.2f}"
        )
        messages: list[BaseMessage] = [
            SystemMessage(content=_SYNTHESIS_PROMPT),
            HumanMessage(content=user_content),
        ]
        invoke_kwargs: dict = {}
        if callback is not None:
            from langchain_core.runnables import RunnableConfig
            invoke_kwargs["config"] = RunnableConfig(callbacks=[callback])
        response = self.model.invoke(messages, **invoke_kwargs)
        return getattr(response, "content", str(response))

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(self, query: str) -> AgentState:
        """Research *query* and return the final :class:`AgentState`.

        Raises:
            LoopDetectedError: When the same query is submitted more than
                ``config.max_identical_tool_calls`` times.
            PIIExposureError: When a credential pattern appears in the
                research output.
        """
        events: list[TraceEvent] = []
        messages: list[BaseMessage] = [HumanMessage(content=query)]
        initial_size = len(messages)
        query_counts: Counter = Counter()

        def _run_loop() -> AgentState:
            nonlocal messages, events

            log.info("Starting run — query: %r", query[:120])
            callback = self._langchain_callback()
            retry_count = 0
            research: ResearchResult = {"summary": "", "sources": []}
            evaluation: EvaluationResult = {
                "faithfulness": 0.0,
                "completeness": 0.0,
                "guardrail_compliance": 0.0,
                "label": "hallucinated",
                "raw_response": "",
            }
            hitl_required = False

            while True:
                # Loop-detection guard
                query_counts[query] += 1
                if query_counts[query] > self.config.max_identical_tool_calls:
                    events.append(self._event("guard_triggered", {
                        "guard": "loop_detected",
                        "query": query,
                        "count": query_counts[query],
                    }))
                    raise LoopDetectedError(
                        f"Query submitted {query_counts[query]} times — "
                        f"limit is {self.config.max_identical_tool_calls}."
                    )

                # Token-explosion guard
                messages = self._check_token_explosion(messages, initial_size, events)

                # Researcher
                events.append(self._event("tool_call", {"tool": "ResearcherAgent", "query": query}))
                research, r_events = self.researcher.run(query, callback=callback)
                events.extend(r_events)

                # PII guard on research output
                self._check_pii(research.get("summary", ""), events)

                messages.append(AIMessage(content=f"[researcher] {research.get('summary', '')}"))

                # Evaluator
                events.append(self._event("tool_call", {"tool": "EvaluatorAgent"}))
                evaluation, e_events = self.evaluator.run(query, research, callback=callback)
                events.extend(e_events)

                faithfulness = evaluation.get("faithfulness", 0.0)

                log.info("Evaluation — faithfulness=%.2f completeness=%.2f label=%s",
                         faithfulness, evaluation.get("completeness", 0), evaluation.get("label"))
                if faithfulness >= self.config.low_confidence_threshold:
                    log.info("Quality acceptable — synthesising final answer")
                    break

                # Low confidence — retry or escalate
                retry_count += 1
                events.append(self._event("guard_triggered", {
                    "guard": "low_confidence",
                    "faithfulness": faithfulness,
                    "retry_count": retry_count,
                }))

                if retry_count > self.config.max_evaluator_retries:
                    hitl_required = True
                    events.append(self._event("guard_triggered", {"guard": "hitl_escalation"}))
                    break

            # Synthesise final answer
            final_answer = self._synthesise(query, research, evaluation, callback=callback)
            messages.append(AIMessage(content=final_answer))

            return AgentState(
                messages=messages,
                trace_events=events,
                research=research,
                evaluation=evaluation,
                retry_count=retry_count,
                hitl_required=hitl_required,
                final_answer=final_answer,
            )

        if self.config.exporter == "langwatch" and self._exporter is not None:
            try:
                with self._exporter.trace(name="Research & Fact-Check"):
                    return _run_loop()
            except Exception:
                pass

        return _run_loop()


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------

def run(query: str, config: Optional[MultiAgentConfig] = None) -> str:
    """Run the full multi-agent pipeline and return the final answer string.

    Intended for quick CLI usage::

        from src.multi_agent.orchestrator import run
        print(run("What are the main observability tools for LLM agents in 2025?"))
    """
    agent = OrchestratorAgent(config=config or MultiAgentConfig())
    state = agent.run(query)
    return state["final_answer"]
