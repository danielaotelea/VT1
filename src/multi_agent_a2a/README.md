# Multi-Agent A2A System (v2)

A distributed variant of the multi-agent system that deploys Researcher and Evaluator
as independent HTTP services communicating over the
[Agent2Agent (A2A) protocol](https://github.com/google-a2a/A2A).

---

## Architecture

```
User
 │  REST POST /chat
 ▼
OrchestratorAgentA2A  (:8002)          — orchestrator.py + backend_a2a.py
 │                         │
 │ A2A JSON-RPC            │ A2A JSON-RPC
 │ (HTTP + OTel headers)   │ (HTTP + OTel headers)
 ▼                         ▼
Researcher Agent (:8011)   Evaluator Agent (:8012)
researcher_service.py      evaluator_service.py
 └─ ResearcherAgent.run()   └─ EvaluatorAgent.run()
```

Each of the three processes is a fully independent Python service. They start separately,
expose an Agent Card at `/.well-known/agent.json`, and communicate exclusively over HTTP.

---

## The A2A Protocol

A2A is an open JSON-RPC protocol for agent-to-agent communication.
Key concepts used in this implementation:

| Concept | Description |
|---|---|
| **Agent Card** | JSON metadata document at `/.well-known/agent.json` describing an agent's identity, skills, and capabilities. |
| **Task** | The unit of work. Created by the server when a `message/send` request arrives. Transitions: `WORKING → COMPLETED / FAILED`. |
| **AgentExecutor** | Server-side abstract class: `execute(context, event_queue)` + `cancel()`. Implementations live in `researcher_service.py` and `evaluator_service.py`. |
| **TaskUpdater** | Helper that enqueues `TaskStatusUpdateEvent` and `TaskArtifactUpdateEvent` onto the event queue. |
| **Data artifact** | Structured JSON payload (not plain text) sent via `new_data_part()` / `get_data_parts()`. Used to exchange `ResearchResult` and `EvaluationResult` dicts. |

Request payload shapes:
```
Researcher:  {"query": str}
             → {"result": ResearchResult, "trace_events": [...]}

Evaluator:   {"query": str, "research": ResearchResult}
             → {"result": EvaluationResult, "trace_events": [...]}
```

SDK: `a2a-sdk[http-server] >= 1.1.0`.

---

## Observability

### A2A protocol specification

The A2A protocol explicitly defines observability as an enterprise-readiness requirement:

> **A2A Clients and Servers *should* participate in distributed tracing systems.**
> Implementations are encouraged to adopt OpenTelemetry and propagate trace context
> through standard W3C Trace Context headers, enabling end-to-end visibility across
> agent workflows.
>
> Reference: [A2A Enterprise-Ready — Tracing, Observability and Monitoring](https://a2a-protocol.org/latest/topics/enterprise-ready/#tracing-observability-and-monitoring)

| Protocol requirement | This implementation |
|---|---|
| Distributed tracing via OTel + W3C headers | `OTelContextMiddleware` + `_otel_headers()` in `protocol.py` |
| Log task ID, session ID, trace context | `trace_id` logged at entry of every agent; `TraceEvent` audit trail in `AgentState` |
| Request latency and error metrics | Latency logged per request; token/cost attributes on every LLM span |

### How exporters are initialised in each service

The three processes initialise their exporters independently — there is no shared exporter
instance across process boundaries.

**Orchestrator (`:8002`)** — exporter set at runtime via the UI dropdown:

```
POST /exporter/phoenix
  → build_exporter(MultiAgentA2AConfig(exporter="phoenix"))
  → LangChainInstrumentor().instrument(tracer_provider=...)
  → _PhoenixAdapter stored as agent._adapter
```

Switching the dropdown calls `POST /exporter/{name}`, which rebuilds the adapter.
Only the orchestrator's synthesis LLM call is covered by this adapter.

**Researcher service (`:8011`) and Evaluator service (`:8012`)** — exporter fixed at startup:

```
EXPORTER_A2A=phoenix python -m src.multi_agent_a2a.researcher_service
  → build_app() reads os.getenv("EXPORTER_A2A", "none")
  → build_exporter(MultiAgentA2AConfig(exporter="phoenix"))
  → LangChainInstrumentor().instrument(tracer_provider=...)
  → adapter attached as agent._adapter
  → ResearcherExecutor reads _adapter.callback(session_id) per request
```

The exporter **cannot be changed without restarting** the service. This is correct
microservice behaviour — services own their configuration.

> **Important:** the UI exporter dropdown does not affect the Researcher or Evaluator
> services. To emit spans from all three processes to the same backend, set `EXPORTER_A2A`
> in `.env` before starting the sub-agent services.

### Verifying exporter status across services

Each service exposes a `/health` endpoint that includes the active exporter:

```json
GET :8002/health  →  {"status": "ok", "service": "orchestrator", "exporter": "phoenix"}
GET :8011/health  →  {"status": "ok", "service": "researcher",   "exporter": "phoenix"}
GET :8012/health  →  {"status": "ok", "service": "evaluator",    "exporter": "none"}
```

The A2A UI polls all three endpoints and renders a live status table:

```
| Service       | Port  | Exporter | |
|---|---|---|---|
| orchestrator  | :8002 | phoenix  | ✓ |
| researcher    | :8011 | phoenix  | ✓ |
| evaluator     | :8012 | none     | ○ |
```

Icons: **✓** exporter active, **○** service reachable but exporter is `none`, **✗** service unreachable.

The table refreshes automatically when the exporter dropdown changes, and a **↻ Refresh status** button is available for manual polling. A mismatch between services (e.g. orchestrator on `phoenix` but evaluator on `none`) means spans from the evaluator will not appear in Phoenix — fix it by restarting the evaluator with `EXPORTER_A2A=phoenix`.

### Supported exporters

| `EXPORTER_A2A` value | Backend | Span linking across services |
|---|---|---|
| `phoenix` | Arize Phoenix | Full parent-child span tree via W3C `traceparent` |
| `langfuse` | Langfuse | Traces grouped by `session_id` (no OTel span hierarchy) |
| `opik` | Comet Opik | Full parent-child span tree via Opik distributed headers (see below) |
| `otel-stdout` | Console (stdout) | Full span tree printed to terminal |
| `none` | — | No tracing |

### Trace hierarchy in Phoenix

When all three services run with `EXPORTER_A2A=phoenix`:

```
Phoenix UI — one unified trace per request
 └─ researcher_call span          ← orchestrator process :8002
      └─ LangChain LLM span       ← researcher process :8011
           └─ tool: web_search
 └─ evaluator_call span           ← orchestrator process :8002
      └─ LangChain LLM span       ← evaluator process :8012
 └─ synthesise LLM span           ← orchestrator process :8002
```

All spans share the same `trace_id`. You can verify propagation in the logs — each
service prints `trace_id=<hex>` at the start of every request. They should all match.

### Trace hierarchy in Opik

Opik uses its own distributed trace headers (`opik_trace_id` / `opik_parent_span_id`)
instead of W3C `traceparent`, so it requires a different mechanism to establish a
parent span before the A2A network calls are made.

**The problem:** `opik_context.get_distributed_trace_headers()` (called in `protocol.py`
before each A2A call) only returns valid headers when there is an active Opik span in the
current process. In our LangGraph routing nodes, spans are created by `OpikTracer` only
during LLM calls — not during the network dispatch steps that follow them. So without
intervention, Opik would receive empty headers and create three independent, unlinked traces.

**The workaround:** `_OpikAdapter.tracked()` wraps the entire graph execution in
`@opik.track`, creating a root Opik span that stays active for the whole request — including
when `_research_node` and `_evaluate_node` call `_otel_headers()`. The sub-agent services
then receive a valid `opik_trace_id` and create their traces as children.

```
Opik UI — without workaround         Opik UI — with workaround (@opik.track)
  trace: researcher  (orphan)           trace: a2a_orchestrator_run
  trace: evaluator   (orphan)             └─ span: researcher (child)
  trace: orchestrator (synthesis only)    └─ span: evaluator  (child)
                                          └─ span: synthesis LLM (child)
```

This is implemented in `_OpikAdapter.tracked()` (`src/multi_agent/exporter.py`) and called
from `OrchestratorAgentA2A.run()` (`orchestrator.py`). For all other adapters, `tracked()`
is a pass-through — the wrapping has no effect and no overhead.

The `thread_id` (Opik's session concept) is set on the root trace via
`opik_context.update_current_trace(thread_id=session_id)` inside the `@opik.track` wrapper,
so all sub-agent spans are grouped under the same session in the Opik UI.

### Session propagation via W3C headers

In v2, the Researcher and Evaluator run in separate processes. A Python `ContextVar`
never crosses a process boundary, so session context must be carried explicitly over HTTP.

| Header | Spec | Purpose |
|---|---|---|
| `traceparent` | [W3C Trace Context](https://www.w3.org/TR/trace-context/) | Links sub-agent spans to the orchestrator's active span as children |
| `baggage` | [W3C Baggage](https://www.w3.org/TR/baggage/) | Carries `session.id` across service boundaries |

Before each A2A call, `_otel_headers(session_id)` in `protocol.py`:
1. Injects `session_id` directly into W3C Baggage.
2. Calls `opentelemetry.propagate.inject(carrier)` to serialise both `traceparent` and `baggage` into HTTP headers.

On the receiving side, `OTelContextMiddleware` on each service:
1. Calls `opentelemetry.propagate.extract(request.headers)` — restores the OTel context so sub-agent spans become children of the orchestrator's span.
2. Reads `session.id` from the baggage header.
3. Calls `using_session(session_id)` (Phoenix) or passes `session_id` to `_adapter.callback()` (Langfuse/Opik).

In addition to OTel spans, each agent appends `TraceEvent` entries to `AgentState`.
These travel back to the orchestrator in the A2A response payload and are merged into
`state["trace_events"]` — a full audit trail reconstructable from state alone,
independent of whether a tracing backend is connected.

---

## Environment variables

All three services read their configuration from `.env` (loaded via `python-dotenv`).

### Required

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key used by all three LLM calls |

### A2A service configuration

| Variable | Default | Description |
|---|---|---|
| `EXPORTER_A2A` | `none` | Exporter for Researcher and Evaluator services. Set before starting them. Must match what you select in the orchestrator UI for cross-service traces. |
| `RESEARCHER_URL` | `http://127.0.0.1:8011` | URL the orchestrator uses to reach the Researcher service |
| `EVALUATOR_URL` | `http://127.0.0.1:8012` | URL the orchestrator uses to reach the Evaluator service |

### Arize Phoenix

| Variable | Default | Description |
|---|---|---|
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://localhost:6006` | Phoenix OTLP collector URL |
| `PHOENIX_PROJECT_NAME_A2A` | `vt1-a2a` | Project name in the Phoenix UI for A2A traces |

### Langfuse

| Variable | Default | Description |
|---|---|---|
| `LANGFUSE_HOST` | `http://localhost:3000` | Langfuse server URL |
| `LANGFUSE_PUBLIC_KEY_A2A` | — | Public key for the A2A Langfuse project |
| `LANGFUSE_SECRET_KEY_A2A` | — | Secret key for the A2A Langfuse project |

### Comet Opik

| Variable | Default | Description |
|---|---|---|
| `OPIK_URL_OVERRIDE` | `http://localhost:5173/api` | Opik API URL |
| `OPIK_PROJECT_NAME_A2A` | `vt1-a2a` | Project name in the Opik UI for A2A traces |

### Logging

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Python log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) for all services |

### Web search (Researcher only)

| Variable | Default | Description |
|---|---|---|
| `TAVILY_API_KEY` | — | Tavily search API key. If not set, DuckDuckGo is used as fallback (no key required) |

---

## Running

Start all four processes in separate terminals. Set `EXPORTER_A2A` before starting the
sub-agent services to enable tracing from all three processes:

```bash
# Terminal 1 — Researcher service (A2A JSON-RPC on :8011)
EXPORTER_A2A=phoenix python -m src.multi_agent_a2a.researcher_service

# Terminal 2 — Evaluator service (A2A JSON-RPC on :8012)
EXPORTER_A2A=phoenix python -m src.multi_agent_a2a.evaluator_service

# Terminal 3 — Orchestrator REST backend (:8002)
uvicorn src.multi_agent_a2a.backend_a2a:app --reload --port 8002

# Terminal 4 — Gradio UI (http://localhost:7862)
python -m src.multi_agent_a2a.ui
```

Alternatively, put `EXPORTER_A2A=phoenix` in `.env` so all services pick it up automatically.

The UI lets you pick an exporter via dropdown and start new sessions. A service status
table shows the active exporter for all three services at a glance — use it to verify
that all processes are aligned before sending a query. Switching the dropdown reconfigures
the orchestrator only and auto-refreshes the status table; the sub-agent services keep
their startup exporter.

Send queries directly to the REST backend:

```bash
curl -X POST http://localhost:8002/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "What are the main LLM observability tools in 2025?", "exporter": "phoenix"}'
```

With Phoenix running (`cd infra/phoenix && docker compose up -d`), open
http://localhost:6006 — you will see a single trace containing spans from all three
processes, grouped under the same `session.id`.

---

## v1 vs v2: what is the same and what differs

### Business logic: identical in both versions

| Aspect | Detail |
|---|---|
| Graph topology | `research → evaluate → [route] → synthesize → END` with retry loop |
| Loop detection guard | Same query submitted > `max_identical_tool_calls` → `LoopDetectedError` |
| PII guard | Credential regex in research output → `PIIExposureError` |
| Low-confidence check | `faithfulness < low_confidence_threshold` → `retry_count++` |
| HITL condition | `faithfulness < threshold AND retry_count > max_evaluator_retries` |
| Routing | `_route_after_evaluation` — identical logic |
| Synthesis step | Identical `_synthesise()` — same prompt, same token/cost tracking |
| State shape | Shared `AgentState` from `src/multi_agent/state.py` |
| Multi-turn | Same `run_turn()` / `reset_history()` pattern |
| API surface | Same `/chat`, `/exporter/{name}`, `/session/{session_id}` endpoints |

### Key differences

**Transport layer:**
```python
# v1 — in-process call
research, r_events = self.researcher.run(query, callback=_callback(config))

# v2 — network call over A2A JSON-RPC
research, r_events = await self._call_agent(self.config.researcher_url, {"query": query})
```

**Sync vs async:** v1 uses sync graph nodes and `graph.invoke()`; v2 uses async nodes and `await graph.ainvoke()`.

**Exporter scope:** In v1, one `build_exporter()` call covers all three agents in the same process. In v2, each process calls `build_exporter()` independently — the orchestrator at runtime when the UI dropdown changes, the sub-agent services once at startup from `EXPORTER_A2A`.

**Trace event label:** v1 records `"tool": "ResearcherAgent"`; v2 records `"tool": "ResearcherAgent (A2A)"` — distinguishable in the `TraceEvent` audit trail.

**Config:** `MultiAgentA2AConfig` inherits all parameters from `MultiAgentConfig` and adds `researcher_url`, `evaluator_url`, and two port fields. All `_A2A`-suffixed env vars override the `_MULTI_AGENT` defaults from the parent class.

---

## File map

| File | Role |
|---|---|
| `config.py` | `MultiAgentA2AConfig` — extends `MultiAgentConfig` with service URLs, ports, and `_A2A`-suffixed env var overrides |
| `middleware.py` | `OTelContextMiddleware` — shared ASGI middleware that extracts W3C `traceparent`, `baggage`, and Opik headers from each incoming request; mounted by both sub-agent services |
| `agent_cards.py` | Single source of truth for Researcher and Evaluator `AgentCard` definitions |
| `protocol.py` | Async `call_agent()` — A2A client, W3C context header injection, session propagation |
| `researcher_service.py` | `ResearcherExecutor` + `build_app()` — A2A service wrapping `ResearcherAgent`; initialises its own exporter at startup |
| `evaluator_service.py` | `EvaluatorExecutor` + `build_app()` — A2A service wrapping `EvaluatorAgent`; initialises its own exporter at startup |
| `orchestrator.py` | `OrchestratorAgentA2A` — async LangGraph driving the two services |
| `backend_a2a.py` | FastAPI REST backend on port 8002; reads exporter from `EXPORTER_A2A` at startup |
| `ui.py` | Gradio chat UI on port 7862 — built directly (not via `src/ui.py`) to include the service status panel; polls `/health` on all three services |
