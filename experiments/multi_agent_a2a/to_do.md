# Multi-Agent A2A System — Experiment To-Do

Tracks what remains before M5 (Round 2 evaluation, A2A v2) is complete.

---

## 1. Run all 5 exporters and collect JSON results 

### `none` — baseline (no infra needed)

```bash
# Terminal 1
EXPORTER_A2A=none python -m src.multi_agent_a2a.researcher_service

# Terminal 2
EXPORTER_A2A=none python -m src.multi_agent_a2a.evaluator_service

# Terminal 3 — experiment runner
python experiments/multi_agent_a2a/run_experiment.py --exporter none --session-id a2a-none-001
```

### `phoenix`

```bash
# Start Phoenix first: cd infra/phoenix && docker compose up -d

# Terminal 1
EXPORTER_A2A=phoenix python -m src.multi_agent_a2a.researcher_service

# Terminal 2
EXPORTER_A2A=phoenix python -m src.multi_agent_a2a.evaluator_service

# Terminal 3
python experiments/multi_agent_a2a/run_experiment.py --exporter phoenix --session-id a2a-phoenix-001
```

### `langfuse`

```bash
# Start Langfuse first: bash infra/langfuse/langfuse-run.sh

# Terminal 1
EXPORTER_A2A=langfuse python -m src.multi_agent_a2a.researcher_service

# Terminal 2
EXPORTER_A2A=langfuse python -m src.multi_agent_a2a.evaluator_service

# Terminal 3
python experiments/multi_agent_a2a/run_experiment.py --exporter langfuse --session-id a2a-langfuse-001
```

### `opik`

```bash
# Start Opik first: ./opik.sh start  (see infra/opik/OPIK-SETUP.md)

# Terminal 1
EXPORTER_A2A=opik python -m src.multi_agent_a2a.researcher_service

# Terminal 2
EXPORTER_A2A=opik python -m src.multi_agent_a2a.evaluator_service

# Terminal 3
python experiments/multi_agent_a2a/run_experiment.py --exporter opik --session-id a2a-opik-001
```

### `otel-stdout`

Unlike the other exporters, otel-stdout prints span JSON to each process's own stdout.
Because A2A runs 3 separate processes, spans are split across 3 terminals.
Pipe each process through `tee` so the span JSON is saved alongside the metrics JSON.

```bash
# Terminal 1 — researcher spans → runs/a2a-otel-stdout-001-researcher.log
EXPORTER_A2A=otel-stdout python -m src.multi_agent_a2a.researcher_service \
  2>&1 | tee experiments/multi_agent_a2a/runs/a2a-otel-stdout-001-researcher.log

# Terminal 2 — evaluator spans → runs/a2a-otel-stdout-001-evaluator.log
EXPORTER_A2A=otel-stdout python -m src.multi_agent_a2a.evaluator_service \
  2>&1 | tee experiments/multi_agent_a2a/runs/a2a-otel-stdout-001-evaluator.log

# Terminal 3 — orchestrator spans + experiment metrics → runs/a2a-otel-stdout-001-orchestrator.log
python experiments/multi_agent_a2a/run_experiment.py --exporter otel-stdout --session-id a2a-otel-stdout-001 \
  2>&1 | tee experiments/multi_agent_a2a/runs/a2a-otel-stdout-001-orchestrator.log
```

Three log files are produced. To verify cross-process propagation, grep for the same `trace_id`
across all three logs — it should appear in all three if W3C context propagation is working.

---
