# Multi-Agent System

A three-agent **Topic Research & Fact-Check** system used as the **Round 2 subject** for tool evaluations.
It exercises every multi-agent coordination pattern studied in Phase 0 and every observability
requirement defined in Phase 1.

> **Status: Milestone 4 — not yet implemented.**
> This README documents the planned architecture and setup so the environment can be prepared in advance.

---

## What it does

The user submits a research question. The system autonomously researches it and returns a cited, evaluated answer.

```
User Input
    │
    ▼
Orchestrator Agent
  - Decomposes the query into sub-tasks
  - Dispatches to Researcher and Evaluator
  - Synthesises the final answer
  - Enforces safety guards (loop detection, HITL escalation)
    │
    ├──► Researcher Agent
    │      Tools: web_search(), fetch_page(), extract_citations()
    │      Returns: { summary, sources: [{url, excerpt}] }
    │
    └──► Evaluator Agent  (LLM-as-judge, GPT-4o-mini, temperature=0)
           Scores: faithfulness · completeness · guardrail_compliance
           Drives: hallucination rate metric + Orchestrator re-routing
```

Safety guards (implemented as LangGraph conditional edges):

| Guard | Trigger | Action |
|---|---|---|
| Loop detection | Same tool called > 3 times | Abort; emit `loop_detected` event |
| Token explosion | Context grows > 2× between steps | Warn; truncate oldest messages |
| Sensitive data | API key / credential pattern in output | Block; emit `pii_detected` event |
| Low confidence | Evaluator faithfulness < 0.6 after 2 retries | Escalate to human (HITL) |

---

## Setup

### 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate      # macOS / Linux
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` at the project root and fill in your keys:

```bash
cp .env.example .env
```

`.env` must contain:

```
OPENAI_API_KEY=sk-...
LANGWATCH_API_KEY=...        # primary tracing platform
```

Additional keys required for the web search tool (added in Milestone 4):

```
# Add one of the following for ResearcherAgent's web_search tool:
TAVILY_API_KEY=...           # recommended
# or SERPAPI_API_KEY=...
```

The agent loads `.env` automatically via `python-dotenv`. Never commit `.env`.

---

## Run (Milestone 4)

From the **project root** with the virtual environment active:

```bash
python -c "
from src.multi_agent.orchestrator import run
result = run('What are the main observability tools for LLM agents in 2025?')
print(result)
"
```

---

## Run the tests (Milestone 4)

```bash
pytest tests/multi_agent/ -v
```

All tests will inject fake sub-agents and run with `exporter="none"` — no API keys required.

---

## Shared state schema (`state.py`)

All agents communicate via `AgentState`, a typed dict passed through the LangGraph graph:

```python
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    trace_events: list[TraceEvent]   # appended by each agent for observability
    research: dict                   # latest ResearcherAgent output
    evaluation: dict                 # latest EvaluatorAgent scores
```

`trace_events` is the coordination audit trail — every agent appends structured events so the
Orchestrator can detect failures and the observability platform can reconstruct the full
multi-agent trace.

---

## Observability

The same platforms evaluated in Round 1 (Arize Phoenix, Langfuse, Comet Opik) are reconnected
to this system. The Round 2 evaluation focuses on:

- Inter-agent span correlation (are all agents visible in one trace?)
- Evaluation metric ingestion (can LangWatch/Langfuse store `faithfulness` scores?)
- Multi-agent dashboard views (session grouping, per-agent cost breakdown)

Experiment runs and results are recorded in `experiments/multi_agent/`.
