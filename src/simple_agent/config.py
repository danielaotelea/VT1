import os
from dataclasses import dataclass, field
from typing import Literal

ExporterName = Literal["langfuse", "phoenix", "opik", "otel-stdout", "none"]


@dataclass
class AgentConfig:
    """Configuration for SimpleAgent.

    Attributes:
        model_name: LangChain model identifier.
        temperature: Sampling temperature for the LLM.
        exporter: Which observability backend to send traces to.
            Defaults to "none" (no tracing) so the agent works without
            any API keys out of the box. Set via AgentConfig(exporter="phoenix")
            or the POST /exporter/{name} endpoint.
        sampling_rate: Fraction of traces to export (0.0–1.0).
        input_token_price_per_million: USD cost per 1M input tokens.
        output_token_price_per_million: USD cost per 1M output tokens.
        max_identical_tool_calls: Maximum times the same tool may be called
            before the loop-detection guard aborts the run.
    """

    model_name: str = "gpt-4o"
    temperature: float = 0
    exporter: ExporterName = "none"
    sampling_rate: float = 1.0

    # Pricing constants (USD per million tokens) — GPT-4o defaults
    input_token_price_per_million: float = 5.0
    output_token_price_per_million: float = 15.0

    # Safety guard
    max_identical_tool_calls: int = 3

    # Observability project names — override via env to separate projects per agent
    phoenix_project_name: str = field(default_factory=lambda: os.getenv("PHOENIX_PROJECT_NAME_SIMPLE_AGENT", "vt1-simple-agent"))
    opik_project_name: str = field(default_factory=lambda: os.getenv("OPIK_PROJECT_NAME_SIMPLE_AGENT", "vt1-simple-agent"))
    langfuse_public_key: str = field(default_factory=lambda: os.getenv("LANGFUSE_PUBLIC_KEY_SIMPLE_AGENT", ""))
    langfuse_secret_key: str = field(default_factory=lambda: os.getenv("LANGFUSE_SECRET_KEY_SIMPLE_AGENT", ""))
