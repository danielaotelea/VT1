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
from string import Template
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from .config import MultiAgentConfig
from .otel_utils import set_token_cost_attributes as _set_token_cost_attributes
from .prompts import PROMPTS
from .state import EvaluationResult, ResearchResult, TraceEvent, make_event


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
            self.model = ChatOpenAI(
                model=self.config.evaluator_model,
                temperature=0,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

    def run(self, query: str, research: ResearchResult, callback=None, runnable_config=None) -> tuple[EvaluationResult, list[TraceEvent]]:
        """Score *research* and return an :class:`EvaluationResult` plus trace events.

        If the LLM returns malformed JSON, all scores default to 0.5 and
        label is "hallucinated" so the Orchestrator will retry safely.
        """
        events: list[TraceEvent] = []

        prompt = Template(PROMPTS.evaluator_judge).substitute(
            query=query,
            summary=research.get("summary", ""),
            sources=self._format_sources(research.get("sources", [])),
        )

        messages = [
            SystemMessage(content=PROMPTS.evaluator_system),
            HumanMessage(content=prompt),
        ]

        if callback is not None:
            invoke_config = RunnableConfig(callbacks=[callback])
        elif runnable_config is not None:
            invoke_config = runnable_config
        else:
            invoke_config = None
        response = self.model.invoke(messages, **({"config": invoke_config} if invoke_config else {}))
        raw = getattr(response, "content", str(response))

        token_payload: dict = {"model": self.config.evaluator_model, "raw_chars": len(raw)}
        usage = getattr(response, "usage_metadata", None)
        if usage:
            input_t = usage.get("input_tokens", 0)
            output_t = usage.get("output_tokens", 0)
            cost = (
                input_t * self.config.input_token_price_per_million / 1_000_000
                + output_t * self.config.output_token_price_per_million / 1_000_000
            )
            token_payload.update({"input_tokens": input_t, "output_tokens": output_t, "cost_usd": cost})
            _set_token_cost_attributes(input_t, output_t, cost)
        events.append(make_event("evaluator","evaluation", token_payload))

        # Parse JSON
        try:
            cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
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
            events.append(make_event("evaluator","guard_triggered", {
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
