# Observability for AI Agents

**VT1 — Semester Project · ZHAW School of Engineering · MSE Programme**  

**Student:** Daniela Otelea · 
**Supervisor:** Dr. Militano Leonardo

A systematic evaluation of three open-source observability platforms — **Arize Phoenix**, **Langfuse**, and **Comet Opik** — against a requirements framework derived from AI agent-specific execution properties: reasoning traceability, tool usage tracking, multi-agent coordination, performance and cost metrics, quality metrics (faithfulness / hallucination rate), and safety governance.

Evaluation is conducted across two progressively complex agent workloads: a single-agent ReAct loop (Round 1) and a distributed three-role Orchestrator→Researcher→Evaluator pipeline over the Google A2A protocol (Round 2).

---

## Table of Contents

- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Agent Implementations](#agent-implementations)
- [Observability Infrastructure](#observability-infrastructure)
- [Running Experiments](#running-experiments)
- [Documentation](#documentation)
- [Test Suite](#test-suite)

---

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env   # add OPENAI_API_KEY at minimum
```

Run an agent without tracing:

```bash
# Simple agent
python -c "
from src.simple_agent.agent import build_agent, main
from src.simple_agent.config import AgentConfig
print(main('What is 6 multiplied by 7?', agent=build_agent(config=AgentConfig(exporter='none'))))
"

# Multi-agent (v1)
python -c "
from src.multi_agent.orchestrator import run
from src.multi_agent.config import MultiAgentConfig
print(run('What are the main observability tools for LLM agents in 2025?', config=MultiAgentConfig(exporter='none')))
"
```

Run all tests (no API keys required):

```bash
pytest tests/   # 63 tests — 18 simple_agent + 27 multi_agent + 18 multi_agent_a2a
```

---

## Project Structure

```
.
├── src/
│   ├── simple_agent/          # Round 1 subject — ReAct loop, 3 arithmetic tools
│   │   ├── agent.py           #   SimpleAgent class + CostTracker + LoopDetectedError
│   │   ├── backend.py         #   FastAPI :8000  (POST /chat, POST /exporter/{name})
│   │   ├── ui.py              #   Gradio :7860
│   │   ├── config.py          #   AgentConfig dataclass
│   │   └── exporter.py        #   ExporterAdapter + Phoenix/Langfuse/Opik subclasses
│   │
│   ├── multi_agent/           # Round 2 subject (v1) — in-process pipeline
│   │   ├── orchestrator.py    #   OrchestratorAgent — dispatch, retry, 4 safety guards
│   │   ├── researcher.py      #   ResearcherAgent  — web search + summarisation
│   │   ├── evaluator.py       #   EvaluatorAgent   — LLM-as-judge (faithfulness, completeness)
│   │   ├── state.py           #   AgentState + TraceEvent audit trail
│   │   ├── backend.py         #   FastAPI :8001
│   │   ├── ui.py              #   Gradio :7861
│   │   ├── config.py          #   MultiAgentConfig
│   │   └── exporter.py        #   same ExporterAdapter pattern as simple_agent
│   │
│   ├── multi_agent_a2a/       # Round 2 subject (v2) — A2A distributed
│   │   ├── orchestrator.py    #   OrchestratorAgentA2A — async, calls agents over HTTP
│   │   ├── researcher_service.py  # Standalone A2A JSON-RPC service :8011
│   │   ├── evaluator_service.py   # Standalone A2A JSON-RPC service :8012
│   │   ├── backend_a2a.py     #   FastAPI :8002
│   │   ├── protocol.py        #   call_agent() — A2A client + W3C header injection
│   │   ├── middleware.py       #   TracingMiddleware — W3C extract + session restore
│   │   ├── agent_cards.py     #   Agent Card definitions (/.well-known/agent.json)
│   │   ├── config.py          #   MultiAgentA2AConfig (extends MultiAgentConfig)
│   │   ├── ui.py              #   Gradio :7862 with service status panel
│   │   └── tracing/           #   Per-tool TracingStrategy (Phoenix/Langfuse/Opik/none)
│   │
│   ├── otel_utils.py          # Shared helpers: set_token_cost_attributes, record_exception
│   └── ui.py                  # Shared Gradio layout helper
│
├── tests/
│   ├── simple_agent/          # 18 tests — fake LLM injected, exporter=none
│   ├── multi_agent/           # 27 tests — guard logic, retry, HITL escalation
│   └── multi_agent_a2a/       # 18 tests — incl. real A2A wire roundtrip test
│
├── experiments/
│   ├── simple_agent/          # run_experiment.py + runs/ (5 JSON result files)
│   ├── multi_agent/           # run_experiment.py + runs/ (5 JSON result files)
│   └── multi_agent_a2a/       # run_experiment.py + runs/ (5 JSON result files)
│
├── infra/
│   ├── phoenix/               # Docker Compose — UI at http://localhost:6006
│   ├── langfuse/              # Docker Compose + langfuse-run.sh — UI at http://localhost:3000
│   └── opik/                  # ./opik.sh start — UI at http://localhost:5173
│
└── docs/                      # Research, evaluation, and final report (see Documentation)
```

---

## Agent Implementations

### Simple Agent (Round 1) — `src/simple_agent/`

A LangChain ReAct loop with three deterministic arithmetic tools. Used as a controlled baseline for Round 1 evaluation: identical queries, identical tool sequences, any difference in what tools capture is purely instrumentation coverage.

```bash
uvicorn src.simple_agent.backend:app --reload --port 8000
python -m src.simple_agent.ui   # Gradio at :7860
```

→ See [`src/simple_agent/README.md`](src/simple_agent/README.md)

---

### Multi-Agent System v1 (Round 2) — `src/multi_agent/`

A three-role Orchestrator→Researcher→Evaluator pipeline running in a single process via LangGraph. The Orchestrator enforces four safety guards: loop detection, PII/credential exposure, token explosion, and HITL escalation after repeated low-faithfulness evaluations.

```bash
uvicorn src.multi_agent.backend:app --reload --port 8001
python -m src.multi_agent.ui   # Gradio at :7861
```

→ See [`src/multi_agent/README.md`](src/multi_agent/README.md) for architecture diagram and configuration.

---

### Multi-Agent System v2 — A2A Distributed — `src/multi_agent_a2a/`

The same pipeline deployed as three independent services communicating over the Google A2A JSON-RPC protocol. The key observability challenge: `session.id` must cross process boundaries, requiring W3C Baggage propagation and per-tool middleware on each receiving service.

```bash
EXPORTER_A2A=phoenix python -m src.multi_agent_a2a.researcher_service   # :8011
EXPORTER_A2A=phoenix python -m src.multi_agent_a2a.evaluator_service    # :8012
uvicorn src.multi_agent_a2a.backend_a2a:app --reload --port 8002
python -m src.multi_agent_a2a.ui   # Gradio at :7862
```

→ See [`src/multi_agent_a2a/README.md`](src/multi_agent_a2a/README.md) for observability setup, per-tool span hierarchy, and environment variables.

---

## Observability Infrastructure

Start the backend before activating its exporter in the UI dropdown:

| Tool | Command | UI |
|---|---|---|
| Arize Phoenix | `cd infra/phoenix && docker compose up -d` | http://localhost:6006 |
| Langfuse | `bash infra/langfuse/langfuse-run.sh` | http://localhost:3000 |
| Comet Opik | `cd infra/opik && ./opik.sh start` | http://localhost:5173 |

The UI dropdown calls `POST /exporter/{name}` to activate a backend; the agent then sends traces to it for all subsequent queries. All three can run simultaneously — each experiment run uses only one at a time.

---

## Running Experiments

Experiment runners execute a fixed query set and write structured JSON to `experiments/*/runs/`:

```bash
# Round 1 — Simple agent (5 arithmetic queries)
python experiments/simple_agent/run_experiment.py --exporter phoenix

# Round 2 — Multi-agent v1 (5 research queries)
python experiments/multi_agent/run_experiment.py --exporter phoenix

# Round 2 — Multi-agent v2 A2A (start all 3 services first)
python experiments/multi_agent_a2a/run_experiment.py --exporter phoenix
```

Valid exporters: `phoenix` · `langfuse` · `opik` · `otel-stdout` · `none`

Raw results and screenshots: `experiments/*/runs/` and `experiments/*/runs/screenshots/`.

---

## Documentation

| Document | Description |
|---|---|
| [`docs/phase-4.1-final-report.md`](docs/phase-4.1-final-report.md) | Final report — requirements, implementation, results, discussion |
| [`docs/phase-4.0-best-practices.md`](docs/phase-4.0-best-practices.md) | 10 best practices + common anti-patterns |
| [`docs/phase-2.2-tool-comparison-summary.md`](docs/phase-2.2-tool-comparison-summary.md) | Cross-tool comparison matrix, key findings, recommendation |
| [`docs/phase-2.1.1-arize-phoenix-evaluation.md`](docs/phase-2.1.1-arize-phoenix-evaluation.md) | Arize Phoenix in-depth evaluation |
| [`docs/phase-2.1.2-langfuse-evaluation.md`](docs/phase-2.1.2-langfuse-evaluation.md) | Langfuse in-depth evaluation |
| [`docs/phase-2.1.3-comet-opik-evaluation.md`](docs/phase-2.1.3-comet-opik-evaluation.md) | Comet Opik in-depth evaluation |
| [`docs/phase-2.0-identify-open-source-tools-for-observability.md`](docs/phase-2.0-identify-open-source-tools-for-observability.md) | Tooling landscape analysis |
| [`docs/phase-1.1-metrics-framework.md`](docs/phase-1.1-metrics-framework.md) | Metrics framework — TP/FP/FN per guard, cost and quality definitions |
| [`docs/phase-1.0-observability-requirements.md`](docs/phase-1.0-observability-requirements.md) | Observability requirements for AI agents |
| [`docs/phase-0-what-is-an-agent.md`](docs/phase-0-what-is-an-agent.md) | Agent architecture background |
| [`docs/STATUS.md`](docs/STATUS.md) | Current project status — task-by-task completion |

---

## Test Suite

No API keys required. Fake LLMs and `exporter=none` are injected throughout.

```bash
pytest tests/ -v

# By module:
pytest tests/simple_agent/    # 18 tests
pytest tests/multi_agent/     # 27 tests
pytest tests/multi_agent_a2a/ # 18 tests
```
