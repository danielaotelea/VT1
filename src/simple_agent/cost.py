"""Token usage tracking and USD cost accumulation for SimpleAgent."""

from dataclasses import dataclass

from src.otel_utils import set_token_cost_attributes as _set_token_cost_attributes

from .config import AgentConfig


@dataclass
class CostRecord:
    """Token usage and computed cost for a single LLM call."""
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

        No-ops silently when the response carries no usage metadata (e.g. fake
        models injected in tests).
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
        _set_token_cost_attributes(input_tokens, output_tokens, cost)

    def total_cost(self) -> float:
        """Total USD cost across all recorded calls."""
        return sum(r.cost_usd for r in self.records)

    def total_tokens(self) -> dict[str, int]:
        """Aggregate input and output token counts."""
        return {
            "input": sum(r.input_tokens for r in self.records),
            "output": sum(r.output_tokens for r in self.records),
        }
