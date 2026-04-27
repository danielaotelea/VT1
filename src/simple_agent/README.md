# Simple Agent

A single-LLM arithmetic agent used as the **Round 1 subject** for tool evaluations.
One ReAct loop with three tools (`add`, `multiply`, `divide`), instrumented with a pluggable observability exporter.

---

## What it does

1. Receives a user prompt (e.g. `"What is 13 + 37?"`).
2. Calls GPT-4o with the arithmetic tools bound.
3. Executes tool calls and feeds results back until a final answer is reached.
4. Emits traces and cost records to the configured observability platform.

Safety guards: **loop detection** (aborts after `max_identical_tool_calls` repeated tool calls) and **cost tracking** (token usage accumulated via `CostTracker`).

---

## Setup

```bash
# From the project root
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in `OPENAI_API_KEY` plus the keys for whichever exporter you want to use. The agent loads `.env` automatically via `python-dotenv`.

---

## Start the backend

```bash
source .venv/bin/activate
uvicorn src.simple_agent.backend:app --reload
```

Backend API at **http://localhost:8000** — logs every request and exporter activation.  
Swagger docs at **http://localhost:8000/docs**.

## Start the UI

In a separate terminal:

```bash
source .venv/bin/activate
python -m src.simple_agent.ui
```

Gradio UI at **http://localhost:7860**.  
Select a tracing exporter from the dropdown — the backend activates it and checks the collector endpoint before accepting requests.

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

Stop commands: append `--stop` to the Langfuse and Phoenix scripts; run `./opik.sh --stop` for Opik.

See per-tool setup guides in `infra/`.

---

## Run the tests

```bash
pytest tests/simple_agent/ -v
```

All 18 tests use a fake model with `exporter="none"` — no API keys required.

---

## Configuration

All options are in `AgentConfig` (`src/simple_agent/config.py`):

| Field | Default | Description |
|---|---|---|
| `model_name` | `"gpt-4o"` | LangChain model identifier |
| `temperature` | `0` | LLM sampling temperature |
| `exporter` | `"langwatch"` | Tracing backend: `langfuse`, `phoenix`, `opik`, `otel-stdout`, `none` |
| `input_token_price_per_million` | `5.0` | USD per 1M input tokens |
| `output_token_price_per_million` | `15.0` | USD per 1M output tokens |
| `max_identical_tool_calls` | `3` | Loop detection threshold |
