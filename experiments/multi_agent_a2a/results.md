# Multi-Agent A2A System — Experiment Results (Round 2, v2)

Populated during Milestone 5 (tool evaluation Round 2).  
System: `src/multi_agent_a2a/` — three standalone processes (orchestrator + researcher + evaluator) communicating over A2A JSON-RPC.  
Baseline exporter: `none` (no observability overhead).

The same 5-query set as `experiments/multi_agent/` is used so v1 (in-process) and v2 (A2A distributed) results are directly comparable.

---

## Standard Query Set

| ID | Type | Prompt (truncated) |
|----|------|-------------------|
| Q1 | A — Focused factual | What is OpenTelemetry and what problem does it solve for distributed systems? |
| Q2 | A — Focused factual | What is the OpenInference semantic convention and how does it extend OpenTelemetry for LLM applications? |
| Q3 | B — Comparative | How does Arize Phoenix compare to Langfuse for tracing LLM agent applications in 2025? |
| Q4 | B — Comparative | What are the differences between callback-based and auto-instrumentation approaches for LLM observability? |
| Q5 | C — Multi-part | What are the main observability requirements for a multi-agent LLM system? Which open-source tools best address those requirements in 2025, and what are their key limitations? |

---

## Run Log

| Session ID | Tool | E2E Latency (ms) | Avg Faithfulness | Total Retries | HITL Escalations | Total Cost (USD) | Errors |
|-----------|------|-----------------|-----------------|--------------|-----------------|-----------------|--------|
| a2a-none-001 | none (baseline) | 64 881 | 0.90 | 5 | 1 | $0.1117 | 0 |
| a2a-otel-stdout-001 | otel-stdout | 49 684 | 0.90 | 4 | 1 | $0.0989 | 0 |
| a2a-phoenix-002 | phoenix | 56 941 | 0.96 | 1 | 0 | $0.0737 | 0 |
| a2a-langfuse-001 | langfuse | 42 408 | 0.90 | 3 | 1 | $0.0869 | 0 |
| a2a-opik-001 | opik | 42 371 | 0.90 | 3 | 1 | $0.0872 | 0 |

---

## A2A vs v1 Latency Overhead

| Metric | v1 `multi_agent` (`round2-none-001`) | v2 `multi_agent_a2a` (`a2a-none-001`) | Δ overhead |
|--------|--------------------------------------|---------------------------------------|------------|
| Total latency (5 queries) | 54 224 ms | 64 881 ms | +10 657 ms |
| Avg latency per query | 10 845 ms | 12 976 ms | +2 131 ms (+20%) |
| Total retries | 3 | 5 | +2 |
| Avg faithfulness | 0.76 | 0.90 | +0.14 |

> Note: The latency difference is influenced by the retry count difference (5 vs 3 retries), which
> adds extra LLM round-trips beyond the A2A HTTP overhead itself. The per-HTTP-round-trip
> overhead is small — the extra retries account for most of the gap. Faithfulness is higher in
> the A2A run, which also explains more retries being resolved rather than escalated.

---

## Per-Tool Observations

### Arize Phoenix

**Pillar 1 — Cross-process trace correlation**
- [ ] All 5 queries produce traces in the UI
- [ ] Each trace shows spans from all three processes: `orchestrator`, `researcher`, `evaluator`
- [ ] Researcher and evaluator spans appear as children of the orchestrator span (W3C `traceparent` propagated correctly)
- [ ] `session.id` (via W3C Baggage) groups all spans under one session view
- [ ] Guard-triggered events (`low_confidence`, `hitl_escalation`) appear as span events on the orchestrator span
- [ ] Retry creates a second researcher+evaluator child pair under the same trace

**Pillar 2 — Capabilities**
- [ ] Faithfulness score visible as span attribute on the evaluator span
- [ ] `openinference.span.kind = "AGENT"` on the root orchestrator span
- [ ] `input.value` / `output.value` on root span (query + final answer)
- [ ] `input.mime_type` / `output.mime_type` on root span
- [ ] `llm.token_count.total/prompt/completion` on synthesis LLM span
- [ ] Source URLs visible in researcher span metadata
- [ ] A2A event-queue noise spans (`a2a.server.events.*`) filtered out by `_DropA2ANoiseSampler`

**Pillar 3 — Operations**
- [ ] Three separate processes all send to the same Phoenix instance
- [ ] UI responsive with cross-process trace trees
- [ ] Session filter works across all three agent processes

**Notes:**

---

### Langfuse

**Pillar 1 — Cross-process trace correlation**
- [ ] All 5 queries produce traces in the UI
- [ ] Each trace links spans from orchestrator, researcher, and evaluator processes
- [ ] `x-langfuse-trace-id` header correctly links sub-agent spans to the root orchestrator trace
- [ ] `session.id` groups all three agents' observations under one session
- [ ] Guard-triggered events appear as observations or span events
- [ ] Retry creates additional observations under the same trace

**Pillar 2 — Capabilities**
- [ ] Faithfulness score visible as span attribute on evaluator observation
- [ ] `input` / `output` on root trace observation (set via `log_io()`)
- [ ] `llm.token_count.total/prompt/completion` on synthesis LLM observation
- [ ] Source URLs visible in researcher observation metadata
- [ ] A2A event-queue noise filtered out by `should_export_span`

**Pillar 3 — Operations**
- [ ] Three separate processes all send to the same Langfuse instance
- [ ] UI responsive with linked cross-process observations
- [ ] Session filter works

**Notes:**

---

### Comet Opik

**Pillar 1 — Cross-process trace correlation**
- [ ] All 5 queries produce traces in the UI
- [ ] `opik_trace_id` / `opik_parent_span_id` headers link researcher and evaluator spans back to the orchestrator trace
- [ ] `thread_id` (= session_id via W3C Baggage) groups traces across processes
- [ ] Guard-triggered events appear in trace metadata
- [ ] Retry creates additional traces under the same thread

**Pillar 2 — Capabilities**
- [ ] Faithfulness score visible on evaluator trace
- [ ] `llm.token_count.total/prompt/completion` on synthesis LLM span
- [ ] Source URLs visible in researcher trace metadata

**Pillar 3 — Operations**
- [ ] Three separate processes all send to the same Opik instance
- [ ] Thread filter works across processes

**Notes:**

---

### OTel stdout

> **Note:** Spans are split across three log files (one per process). Run each service with
> `2>&1 | tee <log-file>` before starting the experiment. See `to_do.md` for exact commands.
> Cross-process propagation is verified by grepping for the same `trace_id` across all three logs.

**Pillar 1 — Stdout span output**
- [ ] `*-researcher.log` contains span JSON for all researcher calls
- [ ] `*-evaluator.log` contains span JSON for all evaluator calls
- [ ] `*-orchestrator.log` contains the root `orchestrator_run` span and synthesis LLM span
- [ ] All three logs share the same `trace_id` for a given query (W3C propagation confirmed)
- [ ] `openinference.span.kind = "AGENT"` present on `orchestrator_run` span in orchestrator log
- [ ] `input.value` / `output.value` / `input.mime_type` / `output.mime_type` on root span

**Pillar 2 — Capabilities**
- [ ] `llm.token_count.total/prompt/completion` on synthesis LLM span in orchestrator log

**Notes:**
