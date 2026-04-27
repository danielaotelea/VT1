# Langfuse — Local Setup

Langfuse is cloned as a separate repo at `../../../langfuse` (relative to the VT1 project root) and started via its own `docker-compose.yml`.

## Prerequisites

- Docker Desktop running
- Langfuse repo present at `/Users/danielaotelea/Documents/ZHAW/Semester3/VT1/langfuse`

If the repo is missing, clone it first:

```bash
cd /Users/danielaotelea/Documents/ZHAW/Semester3/VT1
git clone https://github.com/langfuse/langfuse.git
```

## Start

```bash
bash infra/langfuse/langfuse-run.sh
```

Or manually:

```bash
cd /Users/danielaotelea/Documents/ZHAW/Semester3/VT1/langfuse
docker compose up -d
```

UI is available at **http://localhost:3000** once containers are healthy.

## Stop

```bash
cd /Users/danielaotelea/Documents/ZHAW/Semester3/VT1/langfuse
docker compose down

# Remove data volumes too (destructive — clears all traces):
docker compose down -v
```

## Account & project setup (done)

The following is already configured — no action needed.

1. Open http://localhost:3000 and **Sign in** with your registered account.
2. Organisation: **vt1-agents**
3. Project: **research**
4. API keys have been created and saved to the project root `.env`:

```
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=http://localhost:3000
```

To re-create or rotate keys: go to **Settings → API Keys** inside the `research` project.

## Verify traces appear

```bash
python -c "
from src.simple_agent.agent import build_agent, main
from src.simple_agent.config import AgentConfig
print(main('What is 6 multiplied by 7?', agent=build_agent(config=AgentConfig(exporter='langfuse'))))
"
```

Open http://localhost:3000, navigate to your project's **Traces** view, and confirm a new trace appears.
