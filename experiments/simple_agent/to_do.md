# Simple Agent — Evaluation Gaps (to do before M3 is complete)

Identified after building the experiment runner. These must be done to turn
raw experiment runs into a proper Round 1 evaluation.

---

## 1. Fill Round 1 structure in evaluation docs (HIGH)

**Files:** `docs/phase-2.1.1-arize-phoenix-evaluation.md`,
`docs/phase-2.1.2-langfuse-evaluation.md`,
`docs/phase-2.1.3-comet-opik-evaluation.md`

All three-pillar sections currently say "To be filled after Round 1 experiment
runs — M3". They need concrete prompts aligned to the criteria from
`docs/phase-2.0-identify-open-source-tools-for-observability.md`:

- **Pillar 1**: Native Libraries, Ingestion Formats, Auto-Instrumentation, Data Exporters
- **Pillar 2**: mapped to Phase 1 metrics (latency, token cost, tool calls, loop detection, HITL)
- **Pillar 3**: License, Deployment Model, Performance Overhead, Resource Usage

Without this structure there is no writing scaffold when sitting down after a session.

---

## 2. Expand results.md to cover Pillars 1 and 3 (HIGH)

**File:** `experiments/simple_agent/results.md`

The current checklist only covers "did spans appear" — that is Pillar 2 (capabilities).
Missing:

- **Pillar 1** section: integration friction — SDK connection, auto-captured attributes,
  missing attributes, lines of config required, silent vs loud failure on bad key.
- **Pillar 3** section: setup time, Docker resource usage, UI responsiveness with N traces,
  export/query capability (can you filter by `session.id`? export to CSV/JSON?).

---

## 3. Cross-tool comparison script (MEDIUM)

**File to create:** `experiments/simple_agent/compare_runs.py`

After running all 3 tools there will be multiple JSON result files per tool in `runs/`.
No script exists to read them and generate the side-by-side table required by
`docs/phase-2.2-tool-comparison-summary.md`. Currently that comparison would be done manually.

Script should:
- Accept a list of JSON files or glob pattern
- Read per-query latency / token counts / cost from each
- Produce a cross-tool comparison table (markdown + stdout)
- Flag where tool-reported numbers diverge from the JSON ground truth

---

## 4. Screenshot directory and naming convention (LOW)

**Directory to create:** `experiments/simple_agent/screenshots/<tool>/`

The planning docs mention screenshots as required artefacts but no directory structure
or naming convention exists. Suggested convention:

```
screenshots/
  phoenix/
    round1-001-trace-view.png
    round1-001-session-view.png
    round1-001-span-attributes.png
  langfuse/
    round1-001-trace-view.png
    ...
  opik/
    round1-001-trace-view.png
    ...
```
