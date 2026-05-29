"""Shared OpenTelemetry helpers used by all agents in this project.

Both functions are safe to call regardless of which exporter is active.
When no OTel SDK is initialised, get_current_span() returns a no-op span
and all attribute/status calls are discarded silently.
"""


def record_exception(exc: BaseException) -> None:
    """Record *exc* on the active OTel span and set status to ERROR."""
    from opentelemetry import trace
    from opentelemetry.trace import StatusCode
    span = trace.get_current_span()
    span.record_exception(exc)
    span.set_status(StatusCode.ERROR, str(exc))


def set_token_cost_attributes(input_tokens: int, output_tokens: int, cost_usd: float) -> None:
    """Write token counts and cost to the active OTel span.

    Uses both OTel Gen AI semconv names (gen_ai.usage.*) and OpenInference
    names (llm.token_count.*) for maximum dashboard compatibility.
    """
    from opentelemetry import trace
    span = trace.get_current_span()
    if not span.is_recording():
        return
    span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
    span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
    span.set_attribute("llm.token_count.prompt", input_tokens)
    span.set_attribute("llm.token_count.completion", output_tokens)
    span.set_attribute("cost.usd", cost_usd)


def otel_resource_attrs(service_name: str) -> dict:
    """Return standard OTel resource attributes for this service."""
    import os
    return {
        "service.name": service_name,
        "service.version": "0.1.0",
        "deployment.environment": os.getenv("DEPLOYMENT_ENV", "local"),
    }
