# Multi-Agent System — Experiment Results (Round 2)

Populated during Milestone 5 (tool evaluation Round 2).  
Baseline exporter: `none` (no observability overhead).

---

## Standard Query Set

| ID | Type | Prompt (truncated) |
|----|------|-------------------|
| Q1 | A — Focused factual | What is OpenTelemetry and what problem does it solve for distributed systems? |
| Q2 | A — Focused factual | What is the OpenInference semantic convention and how does it extend OpenTelemetry for LLM applications? |
| Q3 | B — Comparative | How does Arize Phoenix compare to Langfuse for tracing LLM agent applications in 2025? |
| Q4 | B — Comparative | What are the differences between callback-based and auto-instrumentation approaches for LLM observability? |
| Q5 | C — Multi-part | What are the main observability requirements for a multi-agent LLM system? Which open-source tools best address those requirements in 2025, and what are their key limitations? |

**Type definitions:**
- **A — Focused factual**: narrow, well-defined answer; tests single-pass Researcher → Evaluator with high faithfulness.
- **B — Comparative**: requires synthesising multiple sources; tests multi-source citation and faithfulness scoring.
- **C — Multi-part**: several sub-questions in one prompt; most likely to trigger retry or HITL escalation.

---

## Run Log

| Session ID | Tool | E2E Latency (ms) | Avg Faithfulness | Total Retries | HITL Escalations | Total Cost (USD) | Errors |
|-----------|------|-----------------|-----------------|--------------|-----------------|-----------------|--------|

*(Fill after each experiment run. Session IDs follow the pattern `round2-<tool>-001`.)*

---

## Per-Tool Observations

### Arize Phoenix

**Pillar 1 — Integration**
- [ ] All 5 queries produce traces in the UI
- [ ] Parent–child span hierarchy visible: orchestrator → researcher, evaluator, synthesizer
- [ ] `session.id` groups all three agents' spans under one session
- [ ] Guard-triggered events (`low_confidence`, `hitl_escalation`) appear as span events
- [ ] Retry spans distinguishable from first-pass spans

**Pillar 2 — Capabilities**
- [ ] Faithfulness score visible as span attribute on evaluator span
- [ ] Retry count visible per session
- [ ] HITL escalation flag surfaced
- [ ] Guard names visible in span metadata
- [ ] Source URLs visible in researcher span metadata
- [ ] Token usage per agent role visible
- [ ] Cost attribution per agent role visible

**Pillar 3 — Operations**
- [ ] Docker resource usage acceptable under multi-agent load (3× LLM calls vs. Round 1)
- [ ] UI responsive with deeper trace trees
- [ ] Session filter works across all three agent spans

**Notes:**

---

### Langfuse

**Pillar 1 — Integration**
- [ ] All 5 queries produce traces in the UI
- [ ] Parent–child span hierarchy visible: orchestrator → researcher, evaluator, synthesizer
- [ ] `session.id` groups all three agents' spans under one session
- [ ] Guard-triggered events appear as observations or span events
- [ ] Retry spans distinguishable from first-pass spans

**Pillar 2 — Capabilities**
- [ ] Faithfulness score visible as span attribute on evaluator span
- [ ] Retry count visible per session
- [ ] HITL escalation flag surfaced
- [ ] Guard names visible in span metadata
- [ ] Source URLs visible in researcher span metadata
- [ ] Token usage per agent role visible
- [ ] Cost attribution per agent role visible

**Pillar 3 — Operations**
- [ ] Docker resource usage acceptable under multi-agent load
- [ ] UI responsive with deeper trace trees
- [ ] Session filter works across all three agent spans

**Notes:**

---

### Comet Opik

**Pillar 1 — Integration**
- [ ] All 5 queries produce 3 traces per query (researcher, evaluator, synthesizer) grouped under 1 thread
- [ ] `thread_id` (= `session_id`) groups all three traces correctly
- [ ] Guard-triggered events appear in trace metadata
- [ ] Retry creates additional traces under the same thread

**Pillar 2 — Capabilities**
- [ ] Faithfulness score visible as span attribute on evaluator trace
- [ ] Retry count visible per thread
- [ ] HITL escalation flag surfaced
- [ ] Guard names visible in trace metadata
- [ ] Source URLs visible in researcher trace metadata
- [ ] Token usage per trace visible
- [ ] Cost attribution per trace visible

**Pillar 3 — Operations**
- [ ] Docker resource usage acceptable under multi-agent load
- [ ] UI responsive with multiple traces per thread
- [ ] Thread filter works

**Notes:**
