# Arize Phoenix — Evaluation

## Overview

Arize Phoenix is an open-source observability platform for LLM applications. It supports
OpenTelemetry-native tracing via the OpenInference instrumentation layer, and can be run
entirely locally without an account or API key.

Reference: https://www.youtube.com/watch?v=fHGSxOhWO-g&t=306s  
Span → Trace.id → session id hierarchy

---

## Local Installation

### 1. Start the Docker container

```bash
bash infra/phoenix/docker-run.sh
```

This runs `arizephoenix/phoenix:latest` with:
- Port `6006` — web UI at http://localhost:6006
- Port `4317` — OTLP gRPC collector endpoint

The container persists trace data in a named volume (`phoenix_data`) across restarts.

### 2. Install the SDK

```bash
pip install arize-phoenix openinference-instrumentation-langchain
```

### 3. Configure environment variables (optional)

The default OTLP endpoint is `http://localhost:4317`. Override with:

```
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:4317
```

No API key or account is required.

### 4. Connecting to the agent

Use `exporter="phoenix"` in `AgentConfig` / `MultiAgentConfig`:

```python
from src.simple_agent.agent import build_agent
from src.simple_agent.config import AgentConfig

agent = build_agent(config=AgentConfig(exporter="phoenix"))
agent.invoke([HumanMessage(content="What is 6 * 7?")])
```

The agent calls `phoenix.otel.register()` to create a `TracerProvider` pointed at the
Docker container's OTLP endpoint, then passes it to `LangChainInstrumentor().instrument()`.
Every `model.invoke()` and `tool.invoke()` call produces a span automatically — no per-call
callback is needed.

### 5. Verifying traces appear

Open http://localhost:6006 and check that a new trace appears under the `vt1-simple-agent`
project after running the agent.

---

## Known Limitations (OTel Compliance)

| Area | Status | Detail |
|---|---|---|
| OTLP wire protocol | ✅ Native | Uses OTLP/HTTP `/v1/traces` — fully OTel-standard |
| OpenInference span attributes | ✅ Auto | `LangChainInstrumentor` sets `gen_ai.*`, `llm.*`, `openinference.span.kind` on every LLM/tool span |
| `session.id` | ✅ Supported | Injected via `RunnableConfig(metadata={"session.id": ...})` — picked up by OpenInference |
| OTel Resource attributes | ⚠️ Partial | `register(project_name=...)` is called but `SERVICE_NAME`, `SERVICE_VERSION`, `deployment.environment` are not set — traces can't be filtered by service version in the UI |
| Exception recording | ⚠️ Missing | When `LoopDetectedError` or `PIIExposureError` is raised, `span.record_exception()` and `span.set_status(ERROR)` are not called — error runs look identical to successful runs in the timeline |
| Span events for guard triggers | ⚠️ Missing | Internal `TraceEvent` records (loop detected, PII, HITL escalation) are never emitted as OTel span events — guard firings are invisible in Phoenix's trace detail view |
| Token/cost span attributes | ⚠️ Missing | `CostTracker` accumulates cost internally but does not write `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, or `cost.usd` to the active span — cost data is absent from Phoenix's span attribute panel |
| Sampling rate | ⚠️ Unused | `AgentConfig.sampling_rate` is declared but never wired to the `TracerProvider` sampler — all traces are exported regardless |
| `otel-stdout` LangChain instrumentation | ⚠️ Incomplete | The `otel-stdout` exporter creates a `TracerProvider` but does not call `LangChainInstrumentor().instrument()` — no LLM or tool spans appear in stdout output |

---

## Three-pillar evaluation

### Pillar 1: Integration and Instrumentation Capabilities (The "How")

*(To be filled after Round 1 experiment runs — M3)*

### Pillar 2: Capabilities (the "What")

*(To be filled after Round 1 experiment runs — M3)*

### Pillar 3: Operational Considerations (the "Cost")

*(To be filled after Round 1 experiment runs — M3)*

---

## Round 1 Results (Simple Agent)

*(To be filled after ≥5 experiment runs with `src/simple_agent/` — M3)*

## Round 2 Results (Multi-Agent)

*(To be filled after ≥10 experiment runs with `src/multi_agent/` — M5)*
