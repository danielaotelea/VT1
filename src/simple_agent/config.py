from dataclasses import dataclass
from typing import Literal


@dataclass
class AgentConfig:
    """Configuration for SimpleAgent.

    Attributes:
        model_name: LangChain model identifier passed to init_chat_model.
        temperature: Sampling temperature for the LLM.
        exporter: Which observability backend to send traces to.
            "none" disables all tracing (useful for tests).
        sampling_rate: Fraction of traces to export (0.0–1.0).
        verbosity: Controls how much the agent prints to stdout during a run.
        input_token_price_per_million: USD cost per 1M input tokens (for CostTracker).
        output_token_price_per_million: USD cost per 1M output tokens (for CostTracker).
        max_identical_tool_calls: How many times the same tool may be called before
            the loop-detection guard aborts the run.
    """

    model_name: str = "gpt-4o"
    temperature: float = 0
    exporter: Literal["langwatch", "langfuse", "phoenix", "opik", "otel-stdout", "none"] = "langwatch"
    sampling_rate: float = 1.0
    verbosity: Literal["quiet", "normal", "verbose"] = "normal"

    # Pricing constants (USD per million tokens) — GPT-4o defaults
    input_token_price_per_million: float = 5.0
    output_token_price_per_million: float = 15.0

    # Safety guard
    max_identical_tool_calls: int = 3
