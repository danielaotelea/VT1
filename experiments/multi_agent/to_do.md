# Multi-Agent System — Evaluation To-Do

---

## 1. Run all 5 exporters and collect JSON results

No experiment runs exist yet in `runs/`. Must run before any comparison or
doc-filling can happen.

```bash
# From project root (VT1/)
python experiments/multi_agent/run_experiment.py --exporter none     --session-id round2-none-001
python experiments/multi_agent/run_experiment.py --exporter phoenix  --session-id round2-phoenix-001
python experiments/multi_agent/run_experiment.py --exporter langfuse --session-id round2-langfuse-001
python experiments/multi_agent/run_experiment.py --exporter opik     --session-id round2-opik-001
python experiments/multi_agent/run_experiment.py --exporter otel-stdout --session-id round2-otel-stdout-001
```

Start the relevant infra before each run (see `infra/` docker-compose files).

---
