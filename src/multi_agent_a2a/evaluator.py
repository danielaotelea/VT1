"""A2A Evaluator Agent — LangChain LLM-as-judge (faithfulness only).

Scores the faithfulness of a research summary against its source excerpts using
a single LLM judge call via LangChain ChatOpenAI.

Faithfulness (0.0–1.0): fraction of factual claims in the summary that are
explicitly supported by at least one of the retrieved source excerpts.

Using LangChain here (rather than calling OpenAI directly) means the LLM call
is automatically captured by all three observability backends:
  - Phoenix:  LangChainInstrumentor creates an openai.chat span automatically.
  - Langfuse: CallbackHandler returned by get_callback() attaches to the invoke.
  - Opik:     OpikTracer returned by get_callback() links the span to the
              orchestrator's root trace via distributed_headers.

completeness and guardrail_compliance are intentionally not scored:
  - completeness: requires a reference answer, which is unavailable here.
  - guardrail_compliance: enforced deterministically by the orchestrator PII
    regex before this evaluator is ever called.
"""

import json
import logging
from typing import Optional

from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from src.multi_agent.config import MultiAgentConfig
from src.multi_agent.state import EvaluationResult, ResearchResult, TraceEvent, make_event

log = logging.getLogger("multi_agent_a2a.evaluator")

_JUDGE_PROMPT = """\
You are evaluating whether a research summary accurately reflects its source material.

QUERY: {query}

SUMMARY TO EVALUATE:
{summary}

SOURCE EXCERPTS (ground truth):
{contexts}

Rate the faithfulness of the summary: what fraction of the factual claims in the
summary are explicitly supported by at least one source excerpt above?

Return ONLY a JSON object — no markdown, no extra text:
{{"faithfulness": <float 0.0-1.0>, "label": "grounded" or "hallucinated", "reason": "<one sentence>"}}
"""


class FaithfulnessEvaluator:
    """LLM-as-judge evaluator scoring faithfulness via LangChain.

    Parameters
    ----------
    model:
        Injected LangChain chat model (e.g. a fake for tests).
        When None, a ChatOpenAI instance is created from config.
    config:
        Shared MultiAgentConfig (model name, thresholds).
    """

    def __init__(
        self,
        model=None,
        config: Optional[MultiAgentConfig] = None,
    ):
        self.config = config or MultiAgentConfig()
        self._model = model or ChatOpenAI(
            model=self.config.evaluator_model,
            temperature=0,
        )

    def run(
        self,
        query: str,
        research: ResearchResult,
        callback=None,
    ) -> tuple[EvaluationResult, list[TraceEvent]]:
        """Score faithfulness synchronously; wrap with asyncio.to_thread in the service."""
        events: list[TraceEvent] = []

        contexts = [
            s["excerpt"]
            for s in research.get("sources", [])
            if s.get("excerpt")
        ]

        if not contexts:
            log.warning("[evaluator] No source excerpts — cannot verify faithfulness")
            events.append(make_event("evaluator", "evaluation", {
                "faithfulness": 0.0,
                "reason": "no_source_excerpts",
            }))
            return EvaluationResult(
                faithfulness=0.0,
                label="hallucinated",
                raw_response="no_source_excerpts",
                reason="no_source_excerpts",
            ), events

        context_block = "\n\n".join(
            f"[{i + 1}] {ctx}" for i, ctx in enumerate(contexts)
        )
        prompt = _JUDGE_PROMPT.format(
            query=query,
            summary=research.get("summary", ""),
            contexts=context_block,
        )

        invoke_kwargs: dict = {}
        if callback is not None:
            invoke_kwargs["config"] = RunnableConfig(callbacks=[callback])

        response = self._model.invoke(
            [{"role": "user", "content": prompt}],
            **invoke_kwargs,
        )

        raw = response.content.strip()
        faithfulness = 0.5
        reason = ""
        try:
            parsed = json.loads(raw)
            faithfulness = float(parsed.get("faithfulness", 0.5))
            reason = parsed.get("reason", "")
        except (json.JSONDecodeError, ValueError, TypeError):
            log.warning(f"[evaluator] Could not parse judge response: {raw!r}")
            reason = raw

        faithfulness = max(0.0, min(1.0, faithfulness))
        label = "grounded" if faithfulness >= self.config.low_confidence_threshold else "hallucinated"

        log.info(
            f"[evaluator] faithfulness={faithfulness:.3f} label={label!r} "
            f"contexts={len(contexts)} reason={reason!r}"
        )

        events.append(make_event("evaluator", "evaluation", {
            "faithfulness": faithfulness,
            "num_contexts": len(contexts),
            "reason": reason,
        }))

        if faithfulness < self.config.faithfulness_threshold:
            events.append(make_event("evaluator", "guard_triggered", {
                "guard": "low_faithfulness",
                "faithfulness": faithfulness,
                "threshold": self.config.faithfulness_threshold,
            }))

        return EvaluationResult(
            faithfulness=faithfulness,
            label=label,
            raw_response=raw,
            reason=reason,
        ), events
