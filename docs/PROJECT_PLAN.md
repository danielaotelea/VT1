# Project Plan — Observability for AI Agents

> VT1 · ZHAW Semester 3 · 9 ECTS (225–270 hours total workload)

---

## 1. Current State Audit

### 1.1 Completed Work

| Artefact | Status | Est. Hours |
|---|---|---|
| Phase 0 — What is an AI Agent (ReAct, coordination patterns, architecture) | Complete | ~20h |
| Phase 1.0 — Observability requirements (6 areas: traceability, coordination, governance, performance, quality, safety) | Complete | ~20h |
| Phase 1.1 — Core metrics framework (tables, drift types, TP/FP/FN governance math, HITL, DHARMA) | Complete | ~25h |
| Phase 2.0 — Tooling landscape (shortlist of 3 tools, 3-pillar evaluation framework, comparison table) | Complete | ~20h |
| Literature review (DHARMA/ICLR 2026, Vibe AIGC, HITL latency paper, Anthropic eval guide) | Complete | ~10h |
| `src/simple-agent.py` — LangGraph functional API agent with LangWatch tracing | Partial | ~10h |
| Environment setup (`.env`, `requirements.txt`, LangWatch integration) | Complete | ~5h |
| **Subtotal** | | **~110h** |

### 1.2 Remaining Work

**Phase 2 tool evaluations (M3 — requires running experiments):**
- `docs/phase-2.1.1-arize-phoenix-evaluation.md` — structure in place; Round 1 sections to be filled after M3 experiment runs.
- `docs/phase-2.1.2-langfuse-evaluation.md` — same.
- `docs/phase-2.1.3-comet-opik-evaluation.md` — same.

**Resolved technical debt (M2 + M4):**
- `src/simple-agent.py` deleted; replaced by `src/simple_agent/` package.
- `tests/test_lang_graph_simple.py` retired; replaced by `tests/simple_agent/test_agent.py` (18 tests passing).
- Multi-agent system fully implemented: `src/multi_agent/` package with Orchestrator, Researcher, Evaluator, all safety guards, pluggable exporter, 27 tests passing.

**Phase 4 (entirely pending):** best practices document, final report, setup guide.

---

## 2. Evaluation Approach

The tool evaluations are conducted in **two rounds**, using a progressively more complex agent as the test subject. This is the core methodological contribution of the project:

```
Round 1                                Round 2
──────────────────────────────────     ──────────────────────────────────────────
Simple Agent (single LLM + tools)  →  Multi-Agent System (Orchestrator +
                                        Researcher + Evaluator)
        │                                        │
        ▼                                        ▼
Evaluate Arize Phoenix                 Re-evaluate Arize Phoenix
Evaluate Langfuse             with →   Re-evaluate Langfuse           with
Evaluate Comet Opik          this      Re-evaluate Comet Opik        this
        │                     agent           │                        agent
        ▼                                     ▼
Fill Round 1 sections                  Fill Round 2 sections
in evaluation docs                     in evaluation docs
                                               │
                                               ▼
                                       Comparative analysis:
                                       how does each tool handle
                                       the jump from single to
                                       multi-agent complexity?
```

Each evaluation document (`phase-2.1.x-*.md`) contains two sections — one per round — so the evolution of observability capability with agent complexity is visible in a single place.

---

## 3. Agent Architecture

### 3.1 Simple Agent (Round 1 subject)

A single LangGraph agent that demonstrates the baseline observable unit: one LLM reasoning loop with arithmetic tools (`add`, `multiply`, `divide`), instrumented with LangWatch. The goal is to produce a clean, testable, configurable module that the three observability tools can be connected to with minimal integration effort.

This is a deliberate simplification: a predictable agent with deterministic tool outputs makes it easy to verify that a tracing tool is capturing spans correctly, before introducing the complexity of multi-agent coordination.

### 3.2 Multi-Agent System (Round 2 subject)

**Scenario:** A Topic Research & Fact-Check system. The user submits a research question; the system autonomously researches it and returns a cited, evaluated answer. This scenario was chosen because:

1. It exercises every multi-agent coordination pattern from Phase 0 (Orchestrator pattern, sequential/parallel dispatch, iterative refinement).
2. It provides concrete traces for every Phase 1 observability requirement: tool-call spans (Researcher), inter-agent message logs (Orchestrator ↔ agents), hallucination scoring (Evaluator), cost attribution per role, loop detection, HITL escalation.
3. The round-trip from a trivially observable single agent to this system is the comparative axis for the Round 2 tool evaluations.

### 3.3 Agent Roles

```
User Input
    │
    ▼
┌──────────────────────────────────────┐
│           Orchestrator Agent          │
│  - Decomposes research query         │
│  - Dispatches sub-tasks              │
│  - Synthesises final answer          │
│  - Enforces safety guards            │
│  - Routes to HITL on low confidence  │
└────────────────┬─────────────────────┘
                 │ dispatches to
       ┌─────────┴──────────┐
       ▼                    ▼
┌─────────────────┐   ┌──────────────────────────┐
│ Researcher Agent│   │     Evaluator Agent       │
│                 │   │                           │
│ Tools:          │   │ Scores Researcher output: │
│  web_search()   │   │  - faithfulness           │
│  fetch_page()   │   │    (hallucination rate)   │
│  extract_       │   │  - completeness           │
│  citations()    │   │  - guardrail compliance   │
│                 │   │                           │
│ Returns:        │   │ Returns structured eval   │
│  {summary,      │   │ record → stored as        │
│   sources[]}    │   │ LangWatch eval metric     │
└─────────────────┘   └──────────────────────────┘
```

**Orchestrator Agent**
- Entry point. Receives the user query, plans sub-tasks (decompose → dispatch → synthesise), and routes between Researcher and Evaluator.
- Coordination pattern: dynamic orchestration — evaluates `AgentState` after each sub-task to decide the next step.
- Safety responsibilities: loop detection guard (abort after >3 identical tool calls), token explosion guard (warn at >2× token growth per step), HITL escalation when Evaluator `faithfulness` score < 0.6 after two retries.

**Researcher Agent**
- Executes web searches and document retrieval. Returns structured output: `{summary, sources: [{url, excerpt}]}`.
- Tools: `web_search(query)`, `fetch_page(url)`, `extract_citations(text)`.
- One span per tool call (input, output, latency) is emitted to the observability platform.

**Evaluator Agent**
- LLM-as-judge (GPT-4o-mini at temperature=0 for reproducibility). Scores on three dimensions:
  - `faithfulness`: is each claim in the summary grounded in a cited source excerpt?
  - `completeness`: does the answer address all parts of the user query?
  - `guardrail_compliance`: no PII, credentials, or disallowed content in the output.
- Scores stored as named LangWatch evaluations; threshold at 0.8 emits a warning span; below 0.6 triggers Orchestrator re-routing or HITL escalation.

### 3.4 Inter-Agent Communication

All agents share an `AgentState` typed dict passed through the LangGraph `@entrypoint`. Each agent appends to a `messages` list and a `trace_events` list. The Orchestrator reads `trace_events` to detect coordination failures. State is explicit and fully inspectable by any connected observability platform.

---

## 4. Monitoring Strategy

### 4.1 Platform Stack

| Layer | Tool | Justification |
|---|---|---|
| Primary tracing (Round 1 + 2) | LangWatch | Already integrated; native LangGraph callback |
| Evaluated platform A | Arize Phoenix | Local Docker; OTEL-native |
| Evaluated platform B | Langfuse | Local Docker Compose; ClickHouse backend |
| Evaluated platform C | Comet Opik | Local; fastest ingestion in comparison table |
| Export format | OpenTelemetry spans | Vendor-neutral; satisfies Phase 2.0 Pillar 1 criteria |

Each platform is connected to the same agent via its SDK integration. In Round 1 they trace the simple agent; in Round 2 the same platforms trace the multi-agent system without code changes — demonstrating portability.

### 4.2 Cost Tracking

- A `CostTracker` utility wraps each `call_llm` task. After every LLM response it reads `usage_metadata` and appends `{agent_role, model, input_tokens, output_tokens, cost_usd}` to `trace_events`.
- Pricing constants for GPT-4o and GPT-4o-mini are stored in a config file.
- LangWatch's cost dashboard aggregates per session and per agent role, exercising the "Cost Attribution" metric from Phase 1.0 §4.

### 4.3 Hallucination Detection

1. Evaluator Agent sends a `faithfulness` prompt to GPT-4o-mini: *"For each claim in the summary, is it supported by at least one of the provided source excerpts? Return a JSON score 0–1."*
2. Score stored as a LangWatch evaluation: `eval_name="faithfulness"`, `score=<float>`, `label="grounded"/"hallucinated"`.
3. Score < 0.8 → warning span. Score < 0.6 → Orchestrator re-routes to Researcher with explicit instruction to find additional sources.
4. Implements the "Hallucination Rate" metric from Phase 1.0 §5 with an automated feedback loop.

### 4.4 Safety Guards

Implemented as LangGraph conditional edges:

| Guard | Trigger | Action |
|---|---|---|
| Loop detection | Same tool call repeated >3 times | Abort; emit `loop_detected` event; flag for HITL |
| Token explosion | Context grows >2× between steps | Emit `token_explosion_warning`; truncate oldest non-system messages |
| Sensitive data exposure | Regex match for API keys / credentials in output | Block; emit `pii_detected` event; return sanitised response |
| Low confidence escalation | Evaluator `faithfulness` < 0.6 after two Researcher retries | Escalate to human; record HITL intervention rate metric |

### 4.5 Dashboards (LangWatch)

- **Agent Health Dashboard**: end-to-end latency (P95/P99), error rate, token usage per agent role, cost per session.
- **Quality & Safety Dashboard**: hallucination rate over time, guardrail violation counts (TP/FP/FN), loop detection events, HITL intervention rate.

---

## 5. Project Structure

The folder structure reflects the two-phase evaluation methodology: `src/simple_agent/` and `src/multi_agent/` are separate packages so that the single-agent and multi-agent systems can be run and traced independently.

```
VT1/
├── docs/
│   ├── img/
│   ├── meeting-notes/
│   ├── papers/
│   ├── phase-0-what-is-an-agent.md
│   ├── phase-1.0-observability-requirements.md
│   ├── phase-1.1-metrics-framework.md
│   ├── phase-2.0-identify-open-source-tools-for-observability.md
│   ├── phase-2.1.1-arize-phoenix-evaluation.md      ← Round 1 + Round 2 sections
│   ├── phase-2.1.2-langfuse-evaluation.md           ← Round 1 + Round 2 sections
│   ├── phase-2.1.3-comet-opik-evaluation.md         ← Round 1 + Round 2 sections
│   ├── phase-2.2-tool-comparison-summary.md         ← NEW: cross-tool comparison after Round 2
│   ├── planning.md
│   └── PROJECT_PLAN.md
│
├── src/
│   ├── __init__.py
│   │
│   ├── simple_agent/                    ← Round 1 subject
│   │   ├── __init__.py
│   │   ├── agent.py                     ← build_agent() + main(); refactored from simple-agent.py
│   │   └── config.py                    ← AgentConfig: model, exporter, sampling rate, verbosity
│   │
│   └── multi_agent/                     ← Round 2 subject
│       ├── __init__.py
│       ├── state.py                     ← AgentState typed dict, trace_events schema
│       ├── orchestrator.py              ← OrchestratorAgent
│       ├── researcher.py                ← ResearcherAgent + tools
│       └── evaluator.py                 ← EvaluatorAgent (LLM-as-judge)
│
├── tests/
│   ├── simple_agent/
│   │   └── test_agent.py                ← replaces test_lang_graph_simple.py
│   └── multi_agent/
│       ├── test_orchestrator.py
│       ├── test_researcher.py
│       └── test_evaluator.py
│
├── experiments/
│   ├── simple_agent/
│   │   ├── runs/                        ← exported trace JSONs per run
│   │   └── results.md                   ← observations, screenshots, raw data
│   └── multi_agent/
│       ├── runs/
│       └── results.md
│
├── .env.example
├── CLAUDE.md
├── README.md
└── requirements.txt
```

**Key structural decisions:**
- `experiments/` is separate from `src/` and `docs/` — it holds raw artefacts (trace exports, screenshots) that feed the evaluation docs, not source code.
- Each evaluation doc (`phase-2.1.x`) is updated in place with a Round 1 section (after M3) and a Round 2 section (after M5), keeping the comparative view in one document.
- `phase-2.2-tool-comparison-summary.md` is a new doc written after Round 2 to synthesise findings across all three tools for both agent types.
- `src/simple-agent.py` (the current script) is superseded by `src/simple_agent/agent.py` and can be deleted once M2 is complete.

---

## 6. Milestones and ECTS Breakdown

**Total target: ~270 hours** (within the 225–270h range for 9 ECTS at 25–30h/ECTS)

---

### Milestone 1 — Existing Work (Complete)
**~110 hours**

Research and requirements work across Phases 0, 1, and 2.0 as documented in §1.1.

---

### Milestone 2 — Finalise Simple Agent ✅ Complete
**~25 hours | Deliverables: `src/simple_agent/`, `tests/simple_agent/`, passing CI**

| Task | Status |
|---|---|
| `src/simple_agent/agent.py` — `build_agent()`, `main()`, `CostTracker`, `LoopDetectedError` | ✅ |
| `src/simple_agent/config.py` — `AgentConfig` with pluggable exporter | ✅ |
| `src/simple_agent/backend.py` — FastAPI port 8000; `/chat` + `/exporter/{name}`; reachability checks; logging | ✅ |
| `src/simple_agent/ui.py` — Gradio port 7860; exporter dropdown + status; examples table (`gr.Dataset`) | ✅ |
| Exporter fixes: Langfuse 4.x import path, Phoenix OTLP full path, Opik env-driven config | ✅ |
| Structured logging (exporter init, LLM calls, tool calls, response time) | ✅ |
| 18 tests passing (`tests/simple_agent/`) | ✅ |
| `pytest.ini` with `pythonpath = .` | ✅ |

---

### Milestone 3 — Tool Evaluation Round 1 (Simple Agent) 🔄 In Progress
**~30 hours | Deliverables: Round 1 sections in `phase-2.1.1/2/3`, `experiments/simple_agent/results.md`**

Each tool is installed locally and connected to the simple agent. Evaluation follows the 3-pillar framework from `phase-2.0`.

**Infrastructure — ✅ Complete:**

| Task | Status |
|---|---|
| `infra/langfuse/langfuse-run.sh` (start / `--stop`), `LANGFUSE-SETUP.md` | ✅ |
| Langfuse: org `vt1-agents`, project `research`, API keys in `.env`, traces verified | ✅ |
| `infra/phoenix/phoenix-run.sh` (named container, `--stop`), `PHOENIX-SETUP.md` | ✅ |
| Phoenix: project created, `PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006` in `.env` | ✅ |
| `infra/opik/OPIK-SETUP.md` (`./opik.sh` start/stop) | ✅ |
| Opik: project `vt1-simple-agent`, `OPIK_URL_OVERRIDE` + `OPIK_PROJECT_NAME` in `.env` | ✅ |
| All exporter fixes applied to simple agent and multi agent | ✅ |
| All 45 tests passing | ✅ |

**Experiment runs — ⏳ Pending:**

| Task | Hours |
|---|---|
| Arize Phoenix: run ≥5 structured sessions via UI, capture spans, screenshot dashboards | 5h |
| Langfuse: run ≥5 sessions, capture traces and evaluation views | 5h |
| Comet Opik: run ≥5 sessions, capture traces | 5h |
| Fill Round 1 sections in `docs/phase-2.1.1-arize-phoenix-evaluation.md` | 4h |
| Fill Round 1 sections in `docs/phase-2.1.2-langfuse-evaluation.md` | 4h |
| Fill Round 1 sections in `docs/phase-2.1.3-comet-opik-evaluation.md` | 4h |
| Write `experiments/simple_agent/results.md` — raw observations, screenshots, metric coverage | 3h |

Each Round 1 section records: SDK version, integration code, metric coverage against Phase 1.1, ingestion latency, UI/query capability, and open questions for Round 2.

---

### Milestone 4 — Multi-Agent System ✅ Complete
**~50 hours | Deliverable: `src/multi_agent/` package, `tests/multi_agent/`**

| Task | Status |
|---|---|
| `state.py` — `AgentState` TypedDict, `trace_events` schema | ✅ |
| `orchestrator.py` — routing, synthesis, 4 safety guards, all exporter fixes + logging | ✅ |
| `researcher.py` — DuckDuckGo/Tavily web search, page fetch, cited summarisation | ✅ |
| `evaluator.py` — LLM-as-judge (faithfulness, completeness, guardrail compliance) | ✅ |
| `backend.py` — FastAPI port 8001; returns eval scores + HITL flag; exporter reachability checks | ✅ |
| `ui.py` — Gradio port 7861; eval scores inline; examples table; exporter dropdown | ✅ |
| 27 tests passing (`tests/multi_agent/`) | ✅ |

---

### Milestone 5 — Tool Evaluation Round 2 (Multi-Agent) ⏳ Blocked on M3
**~25 hours | Deliverables: Round 2 sections in `phase-2.1.1/2/3`, `phase-2.2-tool-comparison-summary.md`, `experiments/multi_agent/results.md`**

| Task | Hours |
|---|---|
| Run ≥10 multi-agent sessions across ≥3 query types; export traces from all three platforms | 5h |
| Arize Phoenix: assess inter-agent span correlation, session grouping, eval metric ingestion; fill Round 2 section | 6h |
| Langfuse: assess same dimensions; fill Round 2 section | 6h |
| Comet Opik: assess same dimensions; fill Round 2 section | 6h |
| Write `phase-2.2-tool-comparison-summary.md` — cross-tool matrix Round 1 vs Round 2, final recommendation | 2h |

---

### Milestone 6 — Evaluation, Best Practices, Final Report ⏳ Blocked on M3 + M5
**~30 hours | Deliverables: `docs/phase-4.0-best-practices.md`, `docs/phase-4.1-final-report.md`, presentation**

| Task | Hours |
|---|---|
| Analyse experiment data (latency P95/P99, hallucination rate, cost per role, guardrail trigger counts) | 8h |
| Write `docs/phase-4.0-best-practices.md` — tool selection, metric definitions, production recommendations | 8h |
| Write `docs/phase-4.1-final-report.md` — full project summary, setup guide, results, lessons learned | 9h |
| Prepare presentation slides and live demo walkthrough | 5h |

---

### Summary

| Milestone | Content | Status | Hours |
|---|---|---|---|
| M1 | Phases 0, 1, 2.0 — research and requirements | ✅ Complete | ~110h |
| M2 | Simple agent + backend + UI + exporter fixes | ✅ Complete | ~25h |
| M3 | Tool evaluation Round 1 — infra ✅, experiment runs pending | 🔄 In Progress | ~30h |
| M4 | Multi-agent + backend + UI + exporter fixes | ✅ Complete | ~50h |
| M5 | Tool evaluation Round 2 (multi-agent) | ⏳ Blocked on M3 | ~25h |
| M6 | Evaluation, best practices, final report | ⏳ Blocked on M5 | ~30h |
| **Total** | | | **~270h** |

**Immediate next step: start M3 experiment runs** — all three tools are running and verified, the Gradio UI is ready. Run ≥5 sessions per tool with the simple agent and document findings in the evaluation docs.

### Remaining Time Estimate (as of 2026-04-27)

| Milestone | Remaining work | Est. hours |
|---|---|---|
| M3 | ≥5 runs × 3 tools + fill 3 evaluation docs + results.md | ~26h |
| M5 | ≥10 multi-agent runs × 3 tools + Round 2 docs + comparison summary | ~25h |
| M6 | Data analysis + best practices doc + final report + presentation | ~30h |
| **Total remaining** | | **~81h** |

**Completion pace:**
- Full-time (8h/day): ~10 working days (~2 weeks)
- Part-time (3–4h/day): ~3–4 weeks

Critical path: **M3 → M5 → M6** (sequential). All infrastructure and coding is done — remaining work is experiments, documentation, and analysis.

---

## 7. Future Work

### Agent-to-Agent (A2A) Protocol

The current multi-agent implementation uses **in-process direct calls** — the Orchestrator instantiates Researcher and Evaluator as Python objects and calls them via method calls within the same process, communicating through a shared `AgentState` TypedDict.

This is intentional for the scope of this project, but a natural next step for a production system would be adopting [Google's A2A protocol](https://google.github.io/A2A/) (released April 2025). A2A is a network protocol for agent interoperability where each agent:
- is deployed as an **independent service** with its own HTTP endpoint
- exposes an **Agent Card** at `.well-known/agent.json` describing its capabilities
- communicates via **JSON-RPC over HTTP**, enabling cross-service, cross-language, and cross-machine agent coordination

Migrating to A2A would also open new observability dimensions: network-level span correlation across service boundaries, distributed tracing across independently deployed agents, and agent discovery/registry visibility — none of which are exercised by the current in-process design.

---

## 8. Key Risks and Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Web search tool costs spiral in experiment runs | Medium | Use a mock `web_search` returning cached fixtures for unit tests; cap real-search budget per experiment session |
| Platform SDK version changes break integration between M3 and M5 | Low | Pin all SDK versions in `requirements.txt`; the `exporter` config flag isolates platform-specific code |
| Local Docker install of a platform fails or is too slow | Medium | Fall back to cloud-hosted trial tier for evaluation; note the setup friction as a finding in the evaluation doc |
| Evaluator LLM-as-judge prompts are inconsistent across runs | Medium | Fix model to GPT-4o-mini at temperature=0; store raw evaluation responses alongside scores in `experiments/` |
| Round 2 tool evaluations reveal a platform is unsuitable | Low | This is a valid finding, not a failure — document it and adjust the final recommendation accordingly |
