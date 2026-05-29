# Arize Phoenix — Local Setup

Phoenix runs via Docker Compose (`infra/phoenix/docker-compose.yml`).

## Prerequisites

- Docker Desktop running
- `arize-phoenix` and `openinference-instrumentation-langchain` installed (via `requirements.txt`)

## Start / Stop

```bash
# Start (UI at http://localhost:6006) — traces persisted in Docker volume
docker compose -f infra/phoenix/docker-compose.yml up -d

# Stop (data kept in volume)
docker compose -f infra/phoenix/docker-compose.yml down

# Stop and delete all trace data (full reset)
docker compose -f infra/phoenix/docker-compose.yml down -v
```

Trace data is stored in the Docker named volume `phoenix_data` and survives container restarts.

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
