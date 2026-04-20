# Simple Agent

A single-LLM arithmetic agent used as the **Round 1 subject** for tool evaluations.
It demonstrates the baseline observable unit: one ReAct loop with three tools (`add`, `multiply`, `divide`),
instrumented with a pluggable observability exporter.

---

## What it does

1. Receives a user prompt (e.g. `"What is 13 + 37?"`).
2. Calls GPT-4o with the arithmetic tools bound.
3. If the model requests a tool call, executes the tool and feeds the result back.
4. Repeats until the model returns a final answer (no more tool calls).
5. Emits traces, spans, and cost records to the configured observability platform.

Safety guards built into the loop:
- **Loop detection** — aborts if the same tool is called more than `max_identical_tool_calls` times (default: 3).
- **Cost tracking** — accumulates token usage and USD cost per LLM call via `CostTracker`.

---

## Setup

### 1. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate      # macOS / Linux
# .venv\Scripts\activate       # Windows
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
LANGWATCH_API_KEY=...        # only required when exporter="langwatch"
```

The agent loads `.env` automatically via `python-dotenv`. Never commit `.env`.

---

## Run

From the **project root** with the virtual environment active:

```bash
python -c "
from src.simple_agent.agent import main, AgentConfig, build_agent
from src.simple_agent.config import AgentConfig

agent = build_agent(config=AgentConfig(exporter='langwatch'))
print(main('What is 6 multiplied by 7?', agent=agent))
"
```

To disable tracing (no API key needed):

```bash
python -c "
from src.simple_agent.agent import main, build_agent
from src.simple_agent.config import AgentConfig

agent = build_agent(config=AgentConfig(exporter='none'))
print(main('What is 100 divided by 4?', agent=agent))
"
```

---

## Run the tests

```bash
pytest tests/simple_agent/ -v
```

All tests inject a fake model and run with `exporter="none"` — no API keys required.

---

## Configuration

All options are in `AgentConfig` (`src/simple_agent/config.py`):

| Field | Default | Description |
|---|---|---|
| `model_name` | `"gpt-4o"` | LangChain model identifier |
| `temperature` | `0` | LLM sampling temperature |
| `exporter` | `"langwatch"` | Tracing backend: `langwatch`, `langfuse`, `phoenix`, `otel-stdout`, `none` |
| `sampling_rate` | `1.0` | Fraction of traces to export |
| `input_token_price_per_million` | `5.0` | USD cost per 1M input tokens |
| `output_token_price_per_million` | `15.0` | USD cost per 1M output tokens |
| `max_identical_tool_calls` | `3` | Loop detection threshold |

---

## Public API

```python
from src.simple_agent.agent import build_agent, main, SimpleAgent, CostTracker, LoopDetectedError
from src.simple_agent.config import AgentConfig

# Factory
agent: SimpleAgent = build_agent(model=None, tools=None, config=AgentConfig())

# Run and get formatted string
output: str = main("Add 3 and 4.", agent=agent)

# Run and get full message list
from langchain_core.messages import HumanMessage
messages = agent.invoke([HumanMessage(content="Multiply 6 by 7.")])

# Inspect costs after a run
print(agent.cost_tracker.total_cost())    # float (USD)
print(agent.cost_tracker.total_tokens())  # {"input": int, "output": int}
```
