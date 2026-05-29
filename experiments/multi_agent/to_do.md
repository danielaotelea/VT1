# Multi-Agent System — Evaluation Gaps (to do before M5 is complete)

Identified after building the experiment runner. These must be done to turn
raw experiment runs into a proper Round 2 evaluation.

---

## 1. Expand results.md with query set and per-tool checklists (HIGH)

**File:** `experiments/multi_agent/results.md`

The current file has an empty run log table and no structure for qualitative
observations. Needed:

- **Standard query set table** — document the 5 fixed prompts with their type
  (A/B/C) and what a correct answer looks like (mirrors simple-agent results.md
  `## Standard Query Set` section), so evaluation sessions have a reference.

- **Run log columns** — add the multi-agent-specific fields that the runner
  already captures: `avg_faithfulness`, `avg_completeness`, `total_retries`,
  `hitl_escalations`, `guards_fired`.

- **Per-tool checklists** (one section each for Phoenix / Langfuse / Opik) covering:
  - *Trace capture*: all 5 queries produce traces; orchestrator / researcher /
    evaluator spans visible as a parent–child hierarchy; faithfulness and
    completeness scores visible as span attributes; retry spans distinguishable
    from first-pass spans; guard-triggered events appear as spans or events;
    `session.id` groups all agents' spans under one session.
  - *Dashboard / UI capability*: can filter by session; E2E latency breakdown
    across all three agents visible; token usage per agent role visible; cost
    attribution per agent visible; retry behaviour visible (separate sub-traces
    or span sequence).

Without this structure there is no writing scaffold for the evaluation sessions.

---

## 2. Fill Round 2 structure in evaluation docs (HIGH)

**Files:** `docs/phase-2.1.1-arize-phoenix-evaluation.md`,
`docs/phase-2.1.2-langfuse-evaluation.md`,
`docs/phase-2.1.3-comet-opik-evaluation.md`

All three docs have a "Round 2" section that says "To be filled after Round 2
experiment runs — M5". Round 2 differs from Round 1 in meaningful ways that
need dedicated prompts:

- **Pillar 1 (integration)**: Does the tool capture parent–child span
  relationships automatically across the three agents, or does it require manual
  context propagation? How are `TraceEvent` entries surfaced (as span events,
  as separate spans, or not at all)?
- **Pillar 2 (capabilities)**: Multi-agent-specific metrics — faithfulness /
  completeness scores as span attributes, retry count visible per session, HITL
  escalation flag surfaced, guard names visible, source URLs in span metadata.
- **Pillar 3 (operations)**: Docker resource usage scales with multi-agent
  traffic (3× the LLM calls per query vs. Round 1). Does the tool's ingest
  pipeline keep up? Does UI responsiveness degrade with deeper trace trees?

---

## 3. Cross-tool comparison script (MEDIUM)

**File to create:** `experiments/multi_agent/compare_runs.py`

After running all 3 tools there will be multiple JSON result files per tool in
`runs/`. No script exists to produce the side-by-side table required by
`docs/phase-2.2-tool-comparison-summary.md`. Currently that comparison would be
done manually.

Script should:
- Accept a list of JSON files or glob pattern
- Read per-query fields: latency, faithfulness, completeness, retry_count,
  hitl_required, source_count, input_tokens, output_tokens, cost_usd,
  guards_fired
- Produce a cross-tool comparison table (markdown + stdout) aggregated at
  session level (averages for scores, sums for tokens/cost/retries)
- Flag where retry count or HITL escalations differ across tools for the same
  query (a divergence likely means the exporter overhead affected faithfulness
  scoring thresholds or latency)

Mirror structure of the planned `experiments/simple_agent/compare_runs.py` so
both can share a common output format consumed by the summary doc.

---

## 4. Screenshot directory and naming convention (LOW)

**Directory to create:** `experiments/multi_agent/screenshots/<tool>/`

The planning docs require screenshots as artefacts. Multi-agent screenshots need
to cover more views than Round 1 because of the span hierarchy. Suggested naming
convention:

```
screenshots/
  phoenix/
    round2-001-session-overview.png       # session timeline across all 3 agents
    round2-001-orchestrator-span.png      # top-level span with guard attributes
    round2-001-researcher-span.png        # web_search + fetch_page children
    round2-001-evaluator-span.png         # faithfulness / completeness attributes
    round2-001-retry-sequence.png         # retry visible as second sub-trace
  langfuse/
    round2-001-session-overview.png
    round2-001-trace-tree.png
    round2-001-score-attributes.png
    round2-001-retry-sequence.png
  opik/
    round2-001-session-overview.png
    round2-001-trace-tree.png
    round2-001-score-attributes.png
    round2-001-retry-sequence.png
```
