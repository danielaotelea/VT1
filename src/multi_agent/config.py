from dataclasses import dataclass
from typing import Literal


@dataclass
class MultiAgentConfig:
    """Configuration for the multi-agent Research & Fact-Check system.

    Each agent role gets its own model so cost vs. quality trade-offs can be
    tuned independently — e.g. a cheap evaluator model paired with a high-quality
    researcher model.
    """

    # Model selection per role
    orchestrator_model: str = "gpt-4o"
    researcher_model: str = "gpt-4o"
    evaluator_model: str = "gpt-4o-mini"   # cheap judge — must be deterministic
    temperature: float = 0

    # Observability backend (shared across all agents)
    exporter: Literal["langwatch", "langfuse", "phoenix", "opik", "otel-stdout", "none"] = "langwatch"

    # Evaluation thresholds
    faithfulness_threshold: float = 0.8   # below → warning span
    low_confidence_threshold: float = 0.6  # below → retry; still below after retries → HITL

    # Retry / safety limits
    max_evaluator_retries: int = 2
    max_identical_tool_calls: int = 3      # loop detection guard (shared with simple agent)

    # Web search limits
    max_search_results: int = 3
    max_page_chars: int = 1_500           # characters kept per fetched page

    # Pricing (USD per million tokens) — for CostTracker
    input_token_price_per_million: float = 5.0
    output_token_price_per_million: float = 15.0
