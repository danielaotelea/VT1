# Arize Phoenix — Local Setup

Phoenix runs as a single Docker container — no Compose file needed.

## Prerequisites

- Docker Desktop running
- `arize-phoenix` and `openinference-instrumentation-langchain` installed (via `requirements.txt`)

## Start / Stop

```bash
# Start (UI at http://localhost:6006)
bash infra/phoenix/phoenix-run.sh

# Stop
bash infra/phoenix/phoenix-run.sh --stop
```

| Endpoint   | URL                  |
|------------|----------------------|
| UI         | http://localhost:6006 |
| OTLP gRPC  | localhost:4317        |

## First-run project setup (done)

After starting Phoenix for the first time:

1. Open http://localhost:6006
2. Created a new **Project** in the UI for the VT1 evaluation runs.

No API key or account registration is required for self-hosted Phoenix.

## Verify traces appear

```bash
source .venv/bin/activate
python -c "
from src.simple_agent.agent import build_agent, main
from src.simple_agent.config import AgentConfig
print(main('What is 6 multiplied by 7?', agent=build_agent(config=AgentConfig(exporter='phoenix'))))
"
```

Open http://localhost:6006 and confirm a new trace appears in your project.
