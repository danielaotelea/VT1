# Simple Agent — Experiment Runner

Runs the fixed 5-query arithmetic set (Q1–Q5) against SimpleAgent with one observability exporter.
Results are saved as JSON to `runs/<session-id>.json`.

All commands must be run from the **project root** (`VT1/`).

---

## Commands

### No tracing (baseline)
```bash
python experiments/simple_agent/run_experiment.py --exporter none --session-id round1-none-001
```
Runs the agent with tracing disabled. Establishes the baseline latency, token counts, and cost
with zero observability overhead. Use this to measure the instrumentation cost added by each tool.

---

### OTel stdout (no backend required)
```bash
python experiments/simple_agent/run_experiment.py --exporter otel-stdout --session-id round1-otel-stdout-001
```
Exports raw OpenTelemetry spans to the terminal. No Docker needed. Useful for verifying that
span names, attributes (`gen_ai.usage.*`, `llm.token_count.*`, `session.id`), and the trace
hierarchy are correct before connecting a real backend.

---

### Arize Phoenix
```bash
python experiments/simple_agent/run_experiment.py --exporter phoenix --session-id round1-phoenix-001
```
Sends spans to the local Phoenix instance (`http://localhost:6006`).
Start the backend first: `cd infra/phoenix && docker compose up -d`

---

### Langfuse
```bash
python experiments/simple_agent/run_experiment.py --exporter langfuse --session-id round1-langfuse-001
```
Sends traces to the local Langfuse instance (`http://localhost:3000`).
Start the backend first: `bash infra/langfuse/langfuse-run.sh`

---

### Comet Opik
```bash
python experiments/simple_agent/run_experiment.py --exporter opik --session-id round1-opik-001
```
Sends traces to the local Opik instance (`http://localhost:5173`).
Start the backend first: `./opik.sh start` (see `infra/opik/OPIK-SETUP.md`)

---

## Output

Each run saves a JSON file to `runs/<session-id>.json` containing per-query latency,
input/output token counts, cost (USD), and any errors. The `sanity-check.json` file
in `runs/` is the original baseline recorded with `--exporter none`.

The `sanity-check.json` file in `runs/` is an early smoke-test recorded before Round 1
(exporter `none`, no session ID). The proper Round 1 baseline is `round1-none-001.json`.

Qualitative observations (trace capture, UI capabilities, setup friction) are recorded
in `results.md`.
