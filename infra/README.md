# infra — Local Observability Tool Stack

This folder contains the local deployment configs for the three observability platforms evaluated in M3 (Round 1, simple agent) and M5 (Round 2, multi-agent).

```
infra/
├── phoenix/
│   └── docker-run.sh       ← single docker run command (no Compose needed)
├── langfuse/
│   └── docker-compose.yml
└── opik/
    └── docker-compose.yml
```

---

## Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin) installed and running.
- Project Python dependencies installed: `pip install -r requirements.txt`
- A `.env` file at the project root with at least `OPENAI_API_KEY=...`

---

## Arize Phoenix

Phoenix runs as a single container — no Compose file required.

```bash
# Start
bash infra/phoenix/docker-run.sh

# Stop
docker stop arize-phoenix && docker rm arize-phoenix
```

| Endpoint | URL |
|---|---|
| UI | http://localhost:6006 |
| OTLP gRPC | localhost:4317 |

**No `.env` changes needed.** The agent's Phoenix exporter calls `px.launch_app()` which connects to the running container automatically via the default OTLP endpoint.

**Verify spans appear:**
```bash
python -c "
from src.simple_agent.agent import build_agent, main
from src.simple_agent.config import AgentConfig
print(main('What is 6 multiplied by 7?', agent=build_agent(config=AgentConfig(exporter='phoenix'))))
"
```
Open http://localhost:6006 and check that a new trace appears under the default project.

---

## Langfuse

Langfuse requires a Postgres database alongside the server.

```bash
# Start
docker compose -f infra/langfuse/docker-compose.yml up -d

# Stop
docker compose -f infra/langfuse/docker-compose.yml down

# Destroy data volumes too
docker compose -f infra/langfuse/docker-compose.yml down -v
```

| Endpoint | URL |
|---|---|
| UI | http://localhost:3000 |

**First-run setup (once only):**

1. Open http://localhost:3000
2. Register an account (local — no email confirmation needed).
3. Create a project (e.g. `vt1-evaluation`).
4. Go to **Settings → API Keys** and copy the public and secret keys.
5. Add to your project root `.env`:

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000
```

**Verify traces appear:**
```bash
python -c "
from src.simple_agent.agent import build_agent, main
from src.simple_agent.config import AgentConfig
print(main('What is 6 multiplied by 7?', agent=build_agent(config=AgentConfig(exporter='langfuse'))))
"
```
Open http://localhost:3000, navigate to your project's **Traces** view and confirm a new trace appears.

---

## Comet Opik

Opik requires MySQL, ClickHouse, and Redis alongside the backend and frontend.

```bash
# Start
docker compose -f infra/opik/docker-compose.yml up -d

# Stop
docker compose -f infra/opik/docker-compose.yml down

# Destroy data volumes too
docker compose -f infra/opik/docker-compose.yml down -v
```

| Endpoint | URL |
|---|---|
| UI | http://localhost:5173 |
| Backend API | http://localhost:8080 |

**`.env` setup:**

Add to your project root `.env`:
```
OPIK_URL_OVERRIDE=http://localhost:5173/api
```

No account registration is needed for self-hosted mode.

**Verify traces appear:**
```bash
python -c "
from src.simple_agent.agent import build_agent, main
from src.simple_agent.config import AgentConfig
print(main('What is 6 multiplied by 7?', agent=build_agent(config=AgentConfig(exporter='opik'))))
"
```
Open http://localhost:5173 and confirm a new trace appears in the default project.

---

## Running all three at once

Each tool uses different ports so they can run simultaneously:

```bash
bash infra/phoenix/docker-run.sh
docker compose -f infra/langfuse/docker-compose.yml up -d
docker compose -f infra/opik/docker-compose.yml up -d
```

Port summary:

| Tool | UI | Other |
|---|---|---|
| Arize Phoenix | 6006 | 4317 (OTLP gRPC) |
| Langfuse | 3000 | — |
| Comet Opik | 5173 | 8080 (backend API) |
