"""Re-exports from the shared src.otel_utils module.

Kept for backwards compatibility with existing imports inside multi_agent/.
"""
from src.otel_utils import record_exception, set_token_cost_attributes, otel_resource_attrs

__all__ = ["record_exception", "set_token_cost_attributes", "otel_resource_attrs"]
