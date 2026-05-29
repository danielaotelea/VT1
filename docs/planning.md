# Project Task Roadmap

## Phase 0: Understanding what is an AI agent and its components

### Goal: Understand the key components of an AI agent
- [x] Review existing literature on AI agent architectures.
- [x] Define core components (memory, planning, tools, interfaces).
- [x] Summarize findings in a short memo with references.

---

## Phase 1: Observability Requirements Definition

### Goal: Define what to measure and why
- [x] Document key observability requirement areas (reasoning trace, multi-agent coordination, governance, performance, quality, safety).
- [x] For each area, define specific metrics, logs, events, and traces needed.
- [x] Identify retention, privacy, and security requirements.

---

## Phase 2: Tooling Landscape Analysis

### Goal: Identify and evaluate open-source tools for observability
- [x] Produce an inventory of relevant tools (Arize Phoenix, Langfuse, Langfuse, Opik).
- [x] Select a small set of tools to prototype with, and justify the choice.
- [x] Evaluate integration capabilities for each tool.
- [ ] Document strengths, limitations, license constraints, and operational considerations. ← M3 + M5

---

## Phase 3: Implementation and Evaluation

### Goal A: Simple agent with observability — ✅ Complete

- [x] Implement `src/simple_agent/agent.py` — ReAct loop with `add`, `multiply`, `divide` tools.
- [x] Implement `src/simple_agent/config.py` — `AgentConfig` with pluggable exporter.
- [x] Implement `src/simple_agent/backend.py` — FastAPI on port 8000; `/chat` + `/exporter/{name}` endpoints; reachability checks; structured logging.
- [x] Implement `src/simple_agent/ui.py` — Gradio on port 7860; exporter dropdown with live status; examples table.
- [x] Wire all exporters: Langfuse (langfuse 4.x), Arize Phoenix (OTLP HTTP), Comet Opik (env-driven), otel-stdout, none.
- [x] Add logging throughout agent and backend (exporter init, LLM calls, tool calls, response time).
- [x] 18 tests passing (`tests/simple_agent/`).
- [x] `src/simple_agent/README.md` — start backend, start UI, exporter table.

### Goal B: Multi-agent system with observability — ✅ Complete

- [x] Implement `src/multi_agent/orchestrator.py` — `OrchestratorAgent` with all safety guards (loop detection, token explosion, PII, HITL).
- [x] Implement `src/multi_agent/researcher.py` — web search (DuckDuckGo / Tavily fallback) + page fetch + cited summarisation.
- [x] Implement `src/multi_agent/evaluator.py` — LLM-as-judge (faithfulness, completeness, guardrail compliance).
- [x] Implement `src/multi_agent/backend.py` — FastAPI on port 8001; returns evaluation scores + HITL flag; same exporter activation pattern as simple agent.
- [x] Implement `src/multi_agent/ui.py` — Gradio on port 7861; evaluation scores displayed inline; examples table.
- [x] Fix exporters in `OrchestratorAgent`: Langfuse 4.x import, Phoenix full OTLP path, Opik env-driven config.
- [x] Add structured logging throughout orchestrator.
- [x] 27 tests passing (`tests/multi_agent/`).
- [x] `src/multi_agent/README.md` — start backend, start UI, exporter table.

### Goal B2: Observability infrastructure — ✅ Complete

- [x] `infra/langfuse/langfuse-run.sh` — start / `--stop` (cd to cloned repo + docker compose).
- [x] `infra/langfuse/LANGFUSE-SETUP.md` — org `vt1-agents`, project `research`, API keys in `.env`.
- [x] `infra/phoenix/phoenix-run.sh` — named container start / `--stop`.
- [x] `infra/phoenix/PHOENIX-SETUP.md` — project created, `PHOENIX_COLLECTOR_ENDPOINT` in `.env`.
- [x] `infra/opik/OPIK-SETUP.md` — `./opik.sh` start/stop, project `vt1-simple-agent`, env vars in `.env`.
- [x] `infra/README.md` — port summary, per-tool quick start.
- [x] All three tools verified reachable (backend reachability check on exporter activation).

### Goal B3: Tooling verified against simple agent — 🔄 In Progress (M3)

- [x] Langfuse: running, project created, API keys set, traces confirmed in UI.
- [x] Arize Phoenix: running, project created, endpoint confirmed at `http://localhost:6006/v1/traces`.
- [x] Comet Opik: running, project `vt1-simple-agent` created, endpoint confirmed.
- [ ] Run ≥5 structured experiment sessions per tool (simple agent).
- [ ] Export trace data to `experiments/simple_agent/runs/`.
- [ ] Fill Round 1 sections in `docs/phase-2.1.1-arize-phoenix-evaluation.md`.
- [ ] Fill Round 1 sections in `docs/phase-2.1.2-langfuse-evaluation.md`.
- [ ] Fill Round 1 sections in `docs/phase-2.1.3-comet-opik-evaluation.md`.
- [ ] Write `experiments/simple_agent/results.md` — observations, screenshots, raw findings.

### Goal C: Configure visualisation and correlation — 🔄 In Progress (M3 + M5)

- [ ] Capture dashboards per tool showing agent health, latency, tool-call spans.
- [ ] Configure trace correlation between agent actions, tool calls, downstream services.
- [ ] Produce a how-to guide for interpreting dashboards and traces. ← M6

---

## Phase 4: Evaluation, Best Practices and Documentation — ⏳ Pending (M5 + M6)

- [ ] Run ≥10 multi-agent experiment sessions per tool; export traces.
- [ ] Fill Round 2 sections in `docs/phase-2.1.1/2/3-*.md`.
- [ ] Write `docs/phase-2.2-tool-comparison-summary.md` — cross-tool matrix Round 1 vs Round 2.
- [ ] Analyse experiment data (latency P95/P99, hallucination rate, cost per role, guardrail trigger counts).
- [ ] Write `docs/phase-4.0-best-practices.md` — tool selection, metric definitions, production recommendations.
- [ ] Write `docs/phase-4.1-final-report.md` — full project summary, results, lessons learned.
- [ ] Prepare presentation slides and live demo walkthrough.
