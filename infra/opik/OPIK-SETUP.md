# Comet Opik — Local Setup

Opik is cloned as a separate repo at `/Users/danielaotelea/Documents/ZHAW/Semester3/VT1/opik` and started via its own `opik.sh` script.

## Prerequisites

- Docker Desktop running
- Opik repo present at `/Users/danielaotelea/Documents/ZHAW/Semester3/VT1/opik`

If the repo is missing, clone it first:

```bash
cd /Users/danielaotelea/Documents/ZHAW/Semester3/VT1
git clone https://github.com/comet-ml/opik.git
```

## Start / Stop

```bash
# Start (UI at http://localhost:5173)
cd /Users/danielaotelea/Documents/ZHAW/Semester3/VT1/opik
./opik.sh

# Stop
./opik.sh --stop
```

| Endpoint    | URL                       |
|-------------|---------------------------|
| UI          | http://localhost:5173      |
| Backend API | http://localhost:8080      |

No account registration is needed for self-hosted mode.

## Project setup (done)

After starting Opik for the first time, a project was created in the UI:

- **Project:** `vt1-simple-agent`

## `.env` configuration (done)

```
OPIK_URL_OVERRIDE=http://localhost:5173/api
OPIK_PROJECT_NAME=vt1-simple-agent
```

## Verify traces appear

```bash
source .venv/bin/activate
python -c "
from src.simple_agent.agent import build_agent, main
from src.simple_agent.config import AgentConfig
print(main('What is 6 multiplied by 7?', agent=build_agent(config=AgentConfig(exporter='opik'))))
"
```

Open http://localhost:5173, navigate to the `vt1-simple-agent` project, and confirm a new trace appears.
