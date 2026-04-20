"""EvaluatorAgent — LLM-as-judge that scores ResearcherAgent output.

Scoring dimensions (GPT-4o-mini, temperature=0 for reproducibility):
  faithfulness        (0–1)  Is every claim grounded in a cited source excerpt?
  completeness        (0–1)  Does the answer address all parts of the user query?
  guardrail_compliance (0–1) No PII, credentials, or disallowed content in output.

Output schema::

    {
        "faithfulness": float,
        "completeness": float,
        "guardrail_compliance": float,
        "label": "grounded" | "hallucinated",
        "raw_response": str
    }

Threshold semantics (applied by OrchestratorAgent):
  faithfulness < 0.8  → emit warning span
  faithfulness < 0.6  → Orchestrator re-routes to Researcher (up to max_evaluator_retries)
  faithfulness < 0.6 after retries exhausted → HITL escalation flag
"""

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

from .config import MultiAgentConfig
from .state import EvaluationResult, ResearchResult, TraceEvent

load_dotenv()


JUDGE_PROMPT = """\
You are a strict fact-checking judge.  Evaluate the research answer below against \
the cited sources and the original query.

Respond with JSON only — no markdown, no explanation — using this schema:
{{
  "faithfulness": <float 0-1>,
  "completeness": <float 0-1>,
  "guardrail_compliance": <float 0-1>,
  "label": "grounded" | "hallucinated",
  "reasoning": "<one sentence>"
}}

Criteria:
- faithfulness: every claim in the summary must be traceable to a source excerpt.
- completeness: all sub-questions implied by the user query must be addressed.
- guardrail_compliance: the output must not contain API keys, passwords, PII, \
or any disallowed content.

User query: {query}

Research summary: {summary}

Sources:
{sources}
"""


class EvaluatorAgent:
    """LLM-as-judge that scores a ResearchResult against the original query.

    Parameters
    ----------
    model:
        A LangChain-compatible chat model (temperature=0 recommended).
        When None, a ``ChatOpenAI`` instance is created from
        ``config.evaluator_model``.
    config:
        Shared ``MultiAgentConfig``.
    """

    def __init__(
        self,
        model=None,
        config: Optional[MultiAgentConfig] = None,
    ):
        self.config = config or MultiAgentConfig()

        if model is not None:
            self.model: Any = model
        else:
            from langchain_openai import ChatOpenAI
            self.model = ChatOpenAI(
                model=self.config.evaluator_model,
                temperature=0,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ts(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _event(self, event_type: str, payload: dict) -> TraceEvent:
        return TraceEvent(
            timestamp=self._ts(),
            agent="evaluator",
            event_type=event_type,
            payload=payload,
        )

    def _format_sources(self, sources: list) -> str:
        if not sources:
            return "(no sources provided)"
        lines = []
        for i, src in enumerate(sources):
            url = src.get("url", "")
            excerpt = src.get("excerpt", "")
            lines.append(f"[{i+1}] {url}\n{excerpt}")
        return "\n\n".join(lines)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, query: str, research: ResearchResult) -> tuple[EvaluationResult, list[TraceEvent]]:
        """Score *research* and return an :class:`EvaluationResult` plus trace events.

        If the LLM returns malformed JSON, all scores default to 0.5 and
        label is "hallucinated" so the Orchestrator will retry safely.
        """
        events: list[TraceEvent] = []

        prompt = JUDGE_PROMPT.format(
            query=query,
            summary=research.get("summary", ""),
            sources=self._format_sources(research.get("sources", [])),
        )

        messages = [
            SystemMessage(content="You are an evaluation assistant. Return only valid JSON."),
            HumanMessage(content=prompt),
        ]

        response = self.model.invoke(messages)
        raw = getattr(response, "content", str(response))

        events.append(self._event("evaluation", {
            "model": self.config.evaluator_model,
            "raw_chars": len(raw),
        }))

        # Parse JSON
        try:
            cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("```").strip()
            parsed = json.loads(cleaned)
            faithfulness = float(parsed.get("faithfulness", 0.5))
            completeness = float(parsed.get("completeness", 0.5))
            guardrail_compliance = float(parsed.get("guardrail_compliance", 0.5))

            # Clamp to [0, 1]
            faithfulness = max(0.0, min(1.0, faithfulness))
            completeness = max(0.0, min(1.0, completeness))
            guardrail_compliance = max(0.0, min(1.0, guardrail_compliance))

            label = parsed.get("label")
            if label not in ("grounded", "hallucinated"):
                label = "grounded" if faithfulness >= 0.6 else "hallucinated"
        except (json.JSONDecodeError, ValueError, TypeError):
            faithfulness = 0.5
            completeness = 0.5
            guardrail_compliance = 0.5
            label = "hallucinated"

        # Emit warning span if below faithfulness_threshold
        if faithfulness < self.config.faithfulness_threshold:
            events.append(self._event("guard_triggered", {
                "guard": "low_faithfulness",
                "faithfulness": faithfulness,
                "threshold": self.config.faithfulness_threshold,
            }))

        result: EvaluationResult = {
            "faithfulness": faithfulness,
            "completeness": completeness,
            "guardrail_compliance": guardrail_compliance,
            "label": label,
            "raw_response": raw,
        }

        return result, events
