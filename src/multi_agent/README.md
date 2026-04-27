# Multi-Agent System

A three-agent Research & Fact-Check pipeline used as the **Round 2 subject** for tool evaluations.

```
User query
    │
    ▼
OrchestratorAgent
    ├─► ResearcherAgent  (web search + summarisation)
    ├─► EvaluatorAgent   (LLM-as-judge scoring)
    │       faithfulness < threshold → retry (max 2)
    │       retries exhausted       → HITL escalation flag
    └─► Synthesise final answer
```

Safety guards: **loop detection**, **token explosion**, **PII exposure**, **HITL escalation**.

---

## Setup

```bash
# From the project root
source .venv/bin/activate
pip install -r requirements.txt
```

`.env` must contain at minimum:

```
OPENAI_API_KEY=sk-...
```

Optional for web search (falls back to DuckDuckGo if absent):

```
TAVILY_API_KEY=...
```

Exporter-specific keys (add whichever you use):

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000

PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006

OPIK_URL_OVERRIDE=http://localhost:5173/api
OPIK_PROJECT_NAME=vt1-multi-agent
```

---

## Start the backend

```bash
source .venv/bin/activate
uvicorn src.multi_agent.backend:app --reload --port 8001
```

Backend API at **http://localhost:8001** — logs every query, evaluation scores, and exporter activations.  
Swagger docs at **http://localhost:8001/docs**.

## Start the UI

In a separate terminal:

```bash
source .venv/bin/activate
python -m src.multi_agent.ui
```

Gradio UI at **http://localhost:7861**.  
Select a tracing exporter from the dropdown. Each response shows inline evaluation scores (faithfulness, completeness, label) and a HITL warning when confidence is too low.

---

## Observability backends

Start the desired backend before activating its exporter in the UI:

| Exporter | Start command | UI |
|---|---|---|
| Langfuse | `bash infra/langfuse/langfuse-run.sh` | http://localhost:3000 |
| Arize Phoenix | `bash infra/phoenix/phoenix-run.sh` | http://localhost:6006 |
| Comet Opik | `cd /Users/danielaotelea/Documents/ZHAW/Semester3/VT1/opik && ./opik.sh` | http://localhost:5173 |
| otel-stdout | — (no service needed) | terminal |
| none | — | — |

Stop: append `--stop` to the Langfuse and Phoenix scripts; run `./opik.sh --stop` for Opik.

See per-tool setup guides in `infra/`.

---

## Run the tests

```bash
pytest tests/multi_agent/ -v
```

All 27 tests inject fake models and run with `exporter="none"` — no API keys required.

---

## Configuration

All options are in `MultiAgentConfig` (`src/multi_agent/config.py`):

| Field | Default | Description |
|---|---|---|
| `orchestrator_model` | `"gpt-4o"` | Model for synthesis |
| `researcher_model` | `"gpt-4o"` | Model for search & summarisation |
| `evaluator_model` | `"gpt-4o-mini"` | LLM-as-judge model |
| `exporter` | `"langwatch"` | Tracing backend |
| `faithfulness_threshold` | `0.8` | Below → warning span |
| `low_confidence_threshold` | `0.6` | Below → retry; exhausted → HITL |
| `max_evaluator_retries` | `2` | Max retries before HITL escalation |
| `max_identical_tool_calls` | `3` | Loop detection threshold |
| `max_search_results` | `3` | Max web search results per query |
