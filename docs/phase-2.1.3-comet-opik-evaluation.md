# Comet Opik — Evaluation

## Overview

Comet Opik is an open-source LLM observability platform. It can be self-hosted locally via
Docker Compose with no account or API key required. The SDK integrates with LangChain via
an `OpikTracer` callback.

---

## Local Installation

### 1. Start the server

```bash
docker compose -f infra/opik/docker-compose.yml up -d
```

This starts five services: `opik-backend`, `opik-frontend`, `opik-mysql`, `opik-clickhouse`,
and `opik-redis`.

- **Web UI** at http://localhost:5173
- **Backend API** at http://localhost:8080

Data is persisted in named volumes (`opik_mysql_data`, `opik_clickhouse_data`). No account
registration is needed for self-hosted mode.

> **Troubleshooting:** check `docker compose -f infra/opik/docker-compose.yml logs -f`
> if the UI doesn't load within 60s — the backend can take a minute on first launch.

### 2. Configure environment variables

No API key is needed for local self-hosted Opik. Just point the SDK at the local server:

Add to `.env`:
```
OPIK_URL_OVERRIDE=http://localhost:5173/api
OPIK_PROJECT_NAME=vt1-agent
```

### 3. Install the SDK

```bash
pip install opik
```

### 4. Connecting to the agent

Use `exporter="opik"` in `AgentConfig` / `MultiAgentConfig`:

```python
from src.simple_agent.agent import build_agent
from src.simple_agent.config import AgentConfig

agent = build_agent(config=AgentConfig(exporter="opik"))
agent.invoke([HumanMessage(content="What is 6 * 7?")])
```

`opik.configure(use_local=True)` reads `OPIK_URL_OVERRIDE` and `OPIK_PROJECT_NAME` from
the environment. The `OpikTracer` callback is then passed to every `model.invoke()` call.

### 5. Verifying traces appear

Open http://localhost:5173 → **Projects** → `vt1-agent`. Each `agent.invoke()` call should
appear as a trace with LLM and tool spans visible in the trace detail view.

---

## Known Limitations (OTel Compliance)

| Area | Status | Detail |
|---|---|---|
| OTLP wire protocol | ❌ Not native | Opik uses its own REST ingestion API, not OTLP. `OpikTracer` is a LangChain callback that POSTs to `/api/v1/traces` in Opik's own format. |
| OpenInference span attributes | ❌ Not supported | Attribute names follow Opik's own schema — not the OTel Gen AI semconv or OpenInference naming conventions. |
| `session.id` | ⚠️ Indirect | Session ID is passed as `metadata={"session_id": ...}` on `OpikTracer`. This makes it searchable as a metadata field but it is not a first-class session grouping like in Langfuse — the UI may not group traces under a session view automatically. |
| OTel Resource attributes | ❌ Not applicable | No OTel Resource concept. Service name/version/environment are not attached to traces. |
| Exception recording | ⚠️ Missing | `OpikTracer` has no mechanism to flag a trace as errored via OTel status codes. A run that raises `LoopDetectedError` or `PIIExposureError` produces a trace indistinguishable from a successful one in the UI. |
| Span events for guard triggers | ❌ Not supported | Opik has no OTel-style span events. `TraceEvent` guard records (loop detection, PII, HITL escalation) cannot be attached to an Opik trace. |
| Token/cost span attributes | ⚠️ Partial | `OpikTracer` captures token counts from LangChain's `LLMResult` callback. Custom `cost.usd` from `CostTracker` is not attached to spans. |
| Sampling rate | ⚠️ Unused | No sampler concept in the Opik SDK. `AgentConfig.sampling_rate` has no effect. |
| Span kind (`AGENT`, `TOOL`, `CHAIN`) | ⚠️ Implicit | Span types are inferred from LangChain callback event names, not from explicit OTel `openinference.span.kind` attributes. |

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
