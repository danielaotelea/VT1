# Langfuse — Evaluation

## Overview

Langfuse is an open-source LLM observability and evaluation platform. It stores traces,
spans, and evaluation scores in a Postgres + ClickHouse backend. The self-hosted version
is deployed via Docker Compose and requires creating a project in the UI to obtain API keys.

---

## Local Installation

### 1. Start the server

```bash
docker compose -f infra/langfuse/docker-compose.yml up -d
```

This starts:
- **Langfuse web app** at http://localhost:3000
- **PostgreSQL** (internal, data persisted in `langfuse_postgres_data` volume)

First startup downloads images and runs DB migrations. Subsequent starts are fast.

> **Troubleshooting:** if port 3000 is in use, edit `infra/langfuse/docker-compose.yml`
> (`"3000:3000"` → `"3001:3000"`) and update `LANGFUSE_HOST` accordingly.

### 2. Create a project and get API keys

1. Open http://localhost:3000 and register a local account (any email/password).
2. Create a new project (e.g. `vt1-simple-agent`).
3. Go to **Settings → API Keys** and create a key pair.
4. Copy the **Public Key** and **Secret Key**.

### 3. Configure environment variables

Add to `.env`:
```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000
```

### 4. Install the SDK

```bash
pip install langfuse
```

### 5. Connecting to the agent

Use `exporter="langfuse"` in `AgentConfig` / `MultiAgentConfig`:

```python
from src.simple_agent.agent import build_agent
from src.simple_agent.config import AgentConfig

agent = build_agent(config=AgentConfig(exporter="langfuse"))
agent.invoke([HumanMessage(content="What is 6 * 7?")])
```

The `CallbackHandler` is instantiated in `_init_exporter` and passed to every `model.invoke()`
call via `RunnableConfig(callbacks=[...])`. Each tool call and LLM response appears as a
child span under the top-level trace in the Langfuse UI.

### 6. Verifying traces appear

After running the agent, open http://localhost:3000 → your project → **Traces**. You should
see one trace per `agent.invoke()` call with the full span tree visible on click.

---

## Known Limitations (OTel Compliance)

| Area | Status | Detail |
|---|---|---|
| OTLP wire protocol | ❌ Not native | Langfuse uses its own ingestion API, not OTLP. Traces are sent via the Langfuse SDK format, not as OTel spans. There is no OTLP `/v1/traces` endpoint. |
| OpenInference span attributes | ❌ Not supported | Attribute names follow Langfuse's own schema (`input`, `output`, `model`) — not the OTel Gen AI semconv (`gen_ai.request.model`, `gen_ai.usage.input_tokens`, etc.) |
| `session.id` | ✅ First-class | `CallbackHandler(session_id=...)` groups traces natively in the Langfuse UI under a session view |
| OTel Resource attributes | ❌ Not applicable | Langfuse has no concept of OTel Resource — service name/version/environment are not attached to traces |
| Exception recording | ⚠️ Missing | `CallbackHandler` has no mechanism to record `span.record_exception()` or set span status to `ERROR`. An agent run that raises `LoopDetectedError` produces a trace indistinguishable from a successful one. |
| Span events for guard triggers | ❌ Not supported | Langfuse has no OTel-style span events. `TraceEvent` records for guard triggers (loop detection, PII, HITL escalation) cannot be attached to a Langfuse trace. |
| Token/cost span attributes | ⚠️ Partial | Langfuse captures token counts from LangChain's `LLMResult` callback automatically (visible as `usage` on LLM spans). However, custom `cost.usd` from `CostTracker` is not attached. |
| Sampling rate | ⚠️ Unused | No sampler concept in the Langfuse SDK. `AgentConfig.sampling_rate` has no effect — all traces are always sent. |
| Span kind (`AGENT`, `TOOL`, `CHAIN`) | ⚠️ Implicit | Langfuse infers span types from LangChain callback event types, not from explicit OTel `openinference.span.kind` attributes. The hierarchy is correct but not OTel-attributable. |

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
