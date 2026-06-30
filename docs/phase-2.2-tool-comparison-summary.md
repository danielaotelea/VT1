# Tool Comparison Summary

Populated after Milestone 5 (Round 2 evaluations complete).

This document synthesises findings from both evaluation rounds across all three tools.

---

## Architecture comparison

Self-hosting architecture differs significantly across the three tools — this affects setup effort, resource consumption, and failure modes in an evaluation environment.

| Dimension | Arize Phoenix | Langfuse | Comet Opik |
|---|---|---|---|
| **Storage backend** | SQLite (default/dev) or PostgreSQL (production) | PostgreSQL (metadata) + ClickHouse (traces/spans) + Redis + S3/Blob | MySQL (metadata) + ClickHouse (traces/spans) + Redis + MinIO (S3-compatible) |
| **Application services** | 1 container — web UI + OTLP collector + DB | 2 containers — Next.js web + Express worker | 3 services — Java backend + Python backend + Nginx/React frontend |
| **Total Docker services** | 1 | ~5 (web, worker, postgres, clickhouse, redis) | 7+ (java-backend, python-backend, frontend, clickhouse, mysql, redis, minio) |
| **Ingestion model** | Native OTLP (synchronous, direct to DB) | Async, decoupled: SDK → API → S3 + Redis queue → Worker → ClickHouse | Batch async: SDK → batch endpoint → Java backend → ClickHouse async inserts |
| **Backend language** | Python | TypeScript (Next.js + Express) | Java 25 (primary) + Python (evaluator) + TypeScript (UI) |
| **OTel wire protocol (OTLP)** | ✅ Native OTLP/gRPC (port 4317) + HTTP — primary ingestion path, used in this project | ⚠️ Own SDK format used in this project; OTLP endpoint exists at `/api/public/otel/v1/traces` (since v3.22.0) but was not exercised here | ⚠️ Own SDK format used in this project; OTLP endpoint exists at `/api/v1/private/otel/v1/traces` but was not exercised here |
| **Semantic convention (displayed)** | OpenInference (`llm.*`, `openinference.span.kind`) — an OTel-compatible semantic convention used by Arize, distinct from OTel GenAI | Langfuse tool-specific schema (`input`, `output`, `model`) | Opik tool-specific schema |
| **OTel GenAI semconv (`gen_ai.*`)** | ❌ Not natively consumed by any of the three tools at time of writing | ❌ | ❌ |
| **Setup complexity** | Lowest — single `docker run` or Compose with one service | Medium — multiple containers, requires project/API key creation in UI | Highest — most services, slowest cold start |
| **Horizontal scaling** | Load-balanced instances sharing PostgreSQL | Scale web and worker containers independently | Kubernetes-native; Altinity ClickHouse operator with Zookeeper |
| **Multi-tenancy** | One instance = one tenant; separate instances per team | Projects and organisations as first-class concepts | Workspaces |
| **Intended deployment scope** | Lightweight, easy to self-host on Docker, Kubernetes, or cloud. Enterprise features (RBAC, HIPAA, dedicated support) require Arize AX (separate product). | Self-hosted or cloud | Self-hosted or cloud |
| **Self-host/cloud parity** | ⚠️ Phoenix self-hosted is fully functional; enterprise/production features require Arize AX (separate product) | ✅ Self-hosted codebase is documented as near feature-complete relative to Langfuse Cloud | ✅ Self-hosted codebase is documented as near feature-complete relative to Comet Cloud |
| **PII / data masking** | ❌ Not documented | ✅ Personal-data masking controls (masking, deletion, retention) | ❌ Not documented |
| **Architecture reference** | [CITE-PHOENIX-ARCH] | [CITE-LANGFUSE-ARCH] | [CITE-OPIK-ARCH] |

### Key architectural observations

**Phoenix** is the simplest to self-host by a wide margin: one container, SQLite by default, and native OTLP means no SDK translation layer. Phoenix documentation describes it as supporting tracing, evaluation, and experimentation, and it can be self-hosted on Docker, Kubernetes, or cloud. Enterprise features — RBAC, HIPAA compliance, dedicated support, and a proprietary OLAP engine — are available via **Arize AX**, a separate paid product. This project evaluates **Phoenix**, not AX — a relevant scope boundary when reading Arize marketing material.

**Langfuse** introduces a proper async ingestion pipeline (SDK → queue → worker → ClickHouse) that decouples ingestion throughput from query latency. Langfuse documents its self-hosted deployment as near feature-complete relative to cloud. Notable features not present in Phoenix or Opik include: personal-data masking controls (masking, deletion, retention policies), prompt management with a collaborative playground, annotation queues, and 100+ framework integrations. The Langfuse cloud offering (langfuse.com) is a managed deployment of the same codebase.

**Opik** had the most complex self-hosted footprint in this evaluation — `./opik.sh` started 8 containers in the evaluation environment (Java backend, Python evaluator service, MinIO, Zookeeper-coordinated ClickHouse, and others). This produced the longest startup time and highest memory baseline observed. The observed startup complexity and container count in this evaluation suggest a Kubernetes-native deployment target; the container count may differ across versions or deployment configurations.

**Ingestion comparison for this project:** Phoenix is the one most clearly using OTLP as its primary ingestion path in this project. Langfuse and Opik both expose OTLP endpoints but were integrated via their SDK callbacks (`CallbackHandler`, `OpikTracer`) in this project — the callback path was chosen because it mapped more directly to each tool's observation model at the time of integration. The wire format and storage schema therefore differ fundamentally across tools in this project's implementation.

> **Source notes:** Two vendor-authored comparisons were consulted and are treated with appropriate scepticism:
> - https://langfuse.com/resources/engineering/best-phoenix-arize-alternatives — authored by Langfuse; positions Phoenix against Langfuse.
> - https://arize.com/docs/phoenix/resources/frequently-asked-questions/langfuse-alternative-arize-phoenix-vs-langfuse-key-differences — authored by Arize; positions Langfuse against Phoenix.
>
> Factual architecture data from both pages is included where it is independently verifiable. Competitive framing is noted but not reproduced uncritically.

---

## Phoenix vs. Langfuse — vendor perspective

The following is a structured summary of the four comparison dimensions published by Arize in their official Phoenix documentation. As with all vendor-authored comparisons, claims about the competing product should be independently verified.

| Dimension | Phoenix (Arize claim) | Langfuse (Arize claim) | Independent note |
|---|---|---|---|
| **Feature access & pricing** | Prompt Playground, LLM-as-a-Judge, and prompt experiments are fully open-source | Prompt Playground and LLM-as-a-Judge locked behind a paid tier | Partially corroborated: Langfuse free tier limits eval runs and some advanced features; specifics change with pricing updates |
| **Self-hosting complexity** | Single Docker container — "drop-in simple for both experimentation and production monitoring" | Requires ClickHouse, Redis, and S3-compatible storage as separate services | Corroborated: Langfuse Compose runs 5–6 containers (web, worker, postgres, clickhouse, redis, minio); Phoenix runs 1 |
| **Instrumentation strategy** | Owns OpenInference — an OTel-compatible semantic convention layer with built-in instrumentation | Relies on third-party instrumentation libraries | Corroborated: Phoenix ships `openinference-instrumentation-langchain`; Langfuse integration uses `langfuse.langchain.CallbackHandler` (a first-party callback, not a separate lib) |
| **Commercial support & roadmap** | Backed by Arize AI; enterprise path via Arize AX (custom dashboards, semantic querying, dedicated support) | Commercialisation through Langfuse Cloud and paid tiers | Both tools have viable enterprise paths; Arize AX and Langfuse Cloud/Enterprise differ significantly in scope and pricing model |

**Context for this project:** The Arize framing positions Phoenix as simpler to self-host and more open in feature access — both points hold in the evaluation environment (single-container Phoenix vs. six-container Langfuse). Phoenix's current documentation markets it more broadly as an AI observability and evaluation platform supporting Docker, Kubernetes, and cloud self-hosting. Enterprise features (RBAC, HIPAA, dedicated support) require Arize AX — a separate paid product. The claim on the Arize comparison page that "Prompt Playground and LLM-as-a-Judge are locked behind a paid tier" for Langfuse is a vendor claim and should be independently verified before treating it as fact.

---

## Security & Authentication comparison

Authentication maturity differs significantly — relevant for any deployment beyond a local laptop.

| Dimension | Arize Phoenix | Langfuse | Comet Opik |
|---|---|---|---|
| **UI authentication (OSS)** | ❌ None | ✅ Email/Password built-in | ❌ None |
| **Social logins (OSS)** | ❌ None | ✅ Google, GitHub, Microsoft (via Auth.js) | ❌ None |
| **API / ingestion auth** | ⚠️ `PHOENIX_API_KEY` env var (protects API, not UI) | ✅ Project-scoped API key pairs | ❌ None by default |
| **Enterprise SSO** | ❌ Arize AX only (separate product) | ⚠️ Paid (Okta, SAML, OIDC, workspace sync) | ❌ Enterprise plan only (SAML, OIDC, LDAP, OAuth) |
| **RBAC** | ❌ Arize AX only | ⚠️ Paid | ❌ Enterprise plan only |
| **PII / data masking** | ❌ Not documented | ✅ Personal-data masking controls (masking, deletion, retention) | ❌ Not documented |
| **Securing OSS self-host** | Infrastructure-level only (reverse proxy, IAP, ALB auth); `PHOENIX_ENABLE_AUTH=True` available but off by default | Built-in for basic auth; infra for advanced SSO | Infrastructure-level only (NGINX Basic Auth recommended) |

**Summary:** In the sources verified here, Langfuse is the one with the clearest built-in self-hosted authentication and personal-data controls. Phoenix can enable auth via `PHOENIX_ENABLE_AUTH=True` but ships with it disabled; Opik has no auth in its OSS edition. For a production team evaluation, Langfuse reduces the infrastructure overhead of securing the dashboard, though all three can be secured at the infrastructure level.

---

## Alerting & notification integration comparison

Alerting capability differs significantly across tools and deployment modes.

### Notification channels

| Channel | Phoenix (OSS) | Arize AX (Enterprise SaaS) | Langfuse (all tiers) | Opik Cloud | Opik Self-Hosted |
|---|---|---|---|---|---|
| **Email** | ❌ | ✅ (recipients need no AX account) | ⚠️ Billing spend only¹ | ❌ | ❌ |
| **Slack** | ❌ | ✅ | ⚠️ Prompt events only² | ✅ | ⚠️ Unconfirmed³ |
| **PagerDuty** | ❌ | ✅ (simple or manual API key) | ❌ | ✅ | ⚠️ Unconfirmed³ |
| **OpsGenie** | ❌ | ✅ | ❌ | ❌ | ❌ |
| **Microsoft Teams** | ❌ | ✅ (via webhooks + Power Automate) | ❌ | ❌ | ❌ |
| **Generic webhooks** | ❌ | ✅ (any HTTP endpoint) | ⚠️ Prompt events only² | ✅ (n8n, Make.com, custom) | ⚠️ Unconfirmed³ |
| **Prometheus scrape endpoint** | ✅ (`PHOENIX_ENABLE_PROMETHEUS=true`, port 9090) | N/A (SaaS) | ❌ | ❌ | ❌ |
| **Analytics export (dashboards)** | ❌ | ❌ | ✅ PostHog + Mixpanel (no alert delivery) | ❌ | ❌ |

¹ Langfuse email spend alert monitors Langfuse Cloud platform billing cost, not LLM token costs or trace metrics. Available on Cloud only.  
² Langfuse webhook/Slack integration fires only on prompt management events (version created/updated/deleted), not on trace errors, latency, or quality scores.  
³ Opik self-hosted architecture docs reference "automation rules and alert configurations" stored in MySQL but document no alert delivery service. Treat as Cloud-only until confirmed.

### Alert trigger types

| Trigger | Phoenix (OSS) | Arize AX | Langfuse | Opik Cloud | Opik Self-Hosted |
|---|---|---|---|---|---|
| **Trace / span errors** | ❌ | ✅ | ❌ | ✅ | ⚠️ Unconfirmed |
| **Latency threshold** | ❌ | ✅ (static or automatic) | ❌ | ✅ | ⚠️ Unconfirmed |
| **Token / cost threshold** | ❌ | ✅ | ❌ | ✅ | ⚠️ Unconfirmed |
| **LLM quality / eval scores** | ❌ | ✅ (hallucination rate, eval labels) | ❌ | ✅ (feedback scores) | ⚠️ Unconfirmed |
| **Guardrail violations** | ❌ | ✅ | ❌ | ✅ | ⚠️ Unconfirmed |
| **Prompt management events** | ❌ | ❌ | ✅ (created/updated/deleted) | ✅ | ⚠️ Unconfirmed |
| **Experiment completion** | ❌ | ❌ | ❌ | ✅ | ⚠️ Unconfirmed |
| **Platform billing spend** | ❌ | ❌ | ✅ (Cloud only) | ❌ | ❌ |

### Alert configuration capabilities

| Capability | Arize AX | Opik Cloud |
|---|---|---|
| **Threshold modes** | Static or automatic (history-based, configurable sensitivity) | Threshold-based with configurable time windows |
| **Evaluation window** | Configurable (default 24h) | 30–60 second event debounce |
| **Alert frequency** | 5, 10, 15, 30 min, hourly, or API-triggered | Near real-time |
| **Muting / maintenance windows** | ✅ | Not documented |
| **Per-monitor routing** | ✅ Project-level and per-monitor | Project-scoped |
| **Delivery retry** | Not documented | ✅ Exponential backoff |
| **Webhook authentication** | ✅ Custom HTTP headers | ✅ Secret token validation |

### Key observations

**Phoenix OSS has no alerting.** The only hook is the Prometheus scrape endpoint (`PHOENIX_ENABLE_PROMETHEUS=true`, port 9090). This is useful if you already operate a Prometheus + Alertmanager stack, but requires external infrastructure not documented in Phoenix itself. Arize AX is a separate product with six notification channels and sophisticated monitor scheduling — not an upgrade of Phoenix.

**Langfuse's alerting scope is narrow.** Webhooks and Slack notifications fire only on prompt management lifecycle events. There is no native "alert when error rate exceeds X%" or "alert on latency spike" built into Langfuse at any tier. For trace-level alerting, the practical path is to export metrics to PostHog and configure alerts there, or build an external evaluation pipeline with a scheduler.

**Based on the sources verified here, Opik Cloud has the broadest documented alerting surface** — ten trigger event types across three categories, Slack + PagerDuty + generic webhooks, n8n/Make.com compatible, and delivery retry. Self-hosted availability is unconfirmed; do not assume parity with Cloud.

**For production on-call alerting without Arize AX**, the recommended pattern is: instrument with any of the three tools → export aggregated metrics to Prometheus or an analytics platform → configure alerts externally. None of the OSS self-hosted editions offer first-class trace-level alerting to on-call systems out of the box.

---

## Prompt management, playground, and systematic testing

All three platforms — Langfuse, Phoenix, and Opik — offer centralised prompt management, interactive playgrounds, and systematic dataset-based testing. This capability was not exercised in this project (which focuses on tracing and observability for running agents), but is worth noting as a shared baseline: teams evaluating any of the three tools for a production workflow can expect prompt versioning, A/B testing of prompt variants, and the ability to run a curated test set against a prompt without deploying the full agent.

| Capability | Arize Phoenix | Langfuse | Comet Opik |
|---|---|---|---|
| Prompt versioning | ✅ | ✅ | ✅ |
| Interactive playground (test a prompt in the UI) | ✅ | ✅ | ✅ |
| Dataset-based systematic testing | ✅ Experiments tab | ✅ Datasets + Experiments | ✅ Experiments |
| LLM-as-a-Judge evaluation in UI | ✅ | ✅ | ✅ |
| Human annotation queue | ✅ | ✅ | ✅ |

The differentiation between tools on this dimension lies in depth and workflow integration, not availability — all three support the basic lifecycle. Langfuse's prompt management is often cited as the most mature for collaborative team use; Phoenix's is tightly integrated with the tracing and evaluation pipeline; Opik's is designed for rapid iteration with CI/CD hooks.

---

## Comparison matrix

| Dimension | Arize Phoenix | Langfuse | Comet Opik |
|---|---|---|---|
| **Round 1: single-agent span capture** | ✅ Auto — `LangChainInstrumentor` patches all calls globally; zero per-call config. 5/5 queries, 0 errors. | ✅ Per-call callback — `LangfuseCallbackHandler` injected per `model.invoke()`. 5/5 queries, 0 errors. In this run, all trace names showed as "ChatOpenAI" (the LangChain component name). | ✅ Per-call callback — `OpikTracer` injected per `model.invoke()`. 5/5 queries, 0 errors. Trace names show actual query input. |
| **Round 1: cost attribution** | ✅ Server-side from `llm.token_count.*` (OpenInference). Pre-built cost chart in Metrics dashboard. | ✅ Server-side from LLM response metadata. Dedicated Cost Dashboard with cost-by-model breakdown. | ✅ Server-side "estimated cost" in Project Overview dashboard. Labelled as estimate; ~2× lower than CostTracker due to different pricing constants. |
| **Round 1: integration effort** | ✅ Lowest code overhead — `phoenix_register()` + one `LangChainInstrumentor()` call; no per-call injection. No account or API key. | ⚠️ Moderate — 6 containers; project creation and public/secret API key pair required in the UI before any traces can be sent. Per-call callback injection required. | ✅ Lowest setup friction — no account, no API key; two env vars sufficient. Per-call callback injection required. 8 containers but zero credential configuration. |
| **Round 2: inter-agent trace correlation** | ✅ Standard W3C `traceparent` — no tool-specific code on sub-agents. 1 unified trace per query across all three A2A services. | ⚠️ Custom `x-langfuse-trace-id` header — Langfuse-specific code required on both orchestrator and sub-agent sides. 19 separate traces per A2A session (one per LangGraph node execution). | ✅ Proprietary `opik_trace_id`/`opik_parent_span_id` headers — Opik-specific on both sides. 5 unified traces per A2A session (1 per query), structurally equivalent to Phoenix. |
| **Round 2: evaluation metric ingestion** | ❌ Not implemented — `EvaluatorAgent` faithfulness/completeness scores not written to Phoenix. Gap: `phoenix.score()` call after each evaluation step. | ❌ Not implemented — scores not written. Gap: `langfuse.score(trace_id=..., name="faithfulness", value=...)` after each evaluation step. | ❌ Not implemented — scores not written. Gap: `opik.log_feedback_score(trace_id=..., name="faithfulness", value=...)` after each evaluation step. |
| **Round 2: dashboard for multi-agent** | ✅ 1 trace/query with full nested span tree (research → evaluate → synthesize). Sessions tab shows latency percentiles per session. Guard events not visible as span events. | ⚠️ 19 traces/session (one per LangGraph node); session view re-groups them but requires navigation. No `langgraph_node` in filterable metadata. Pre-built Cost and Latency dashboards. | ✅ 5 traces/session (A2A), 1 per query. `langgraph_node` in filterable span metadata. Threads view renders full conversation chat-style. Guard metadata (`hitl_required`, `retry_count`) visible on A2A traces via `@opik.track` wrapper. |
| **Licence** | ELv2 — self-hosting free; commercial redistribution restricted. Enterprise features (RBAC, SSO, HIPAA) require Arize AX (separate paid product). | MIT — most permissive. Full self-hosted version free with no feature restrictions; documented as feature-equivalent to Langfuse Cloud. | Apache 2.0 — same as Phoenix. Full self-hosted version free with no feature restrictions; documented as feature-equivalent to Comet Cloud. |
| **Self-host complexity** | ✅ Lowest — 1 container, SQLite default, `docker compose up`. Near-real-time ingestion. | ⚠️ Medium — 6 containers (web, worker, postgres, clickhouse, redis, minio). Async ingestion pipeline; 1–3 s trace delay. Manual project + API key setup required. | ❌ Highest — 8 containers (java-backend, python-backend, frontend, mysql, clickhouse, zookeeper, redis, minio). Kubernetes-native design; longest cold start of the three. |
| **Prompt management & playground** | ✅ Prompt versioning, interactive playground, LLM-as-Judge evaluators, human annotation queue. Tightly integrated with tracing and evaluation pipeline. | ✅ Prompt versioning, collaborative playground, LLM-as-Judge, annotation queues. Most mature for team-based prompt iteration; version lifecycle events trigger webhooks. | ✅ Prompt versioning, interactive playground, LLM-as-Judge, annotation queues. Designed for rapid iteration with CI/CD experiment hooks. |
| **Datasets & experimentation** | ✅ Experiments tab for systematic dataset-based testing; compare prompt variants across runs. | ✅ Datasets + Experiments; A/B prompt testing; experiment comparison views. | ✅ Experiments with CI/CD hooks; dataset management; supports automated regression testing on prompt changes. |
| **GitHub activity & community** | ✅ Active OSS project (`Arize-ai/phoenix`); backed by Arize AI; strong ML observability roots. | ✅ Largest community of the three; very active `langfuse/langfuse` repo; extensive third-party integrations (100+). | ✅ Active OSS project (`comet-ml/opik`); backed by Comet ML with an established MLOps community. |
| **Overall recommendation** | Best for OTel-native pipelines and simplest self-hosting. Zero per-call instrumentation, W3C-standard A2A correlation. Enterprise/production features require Arize AX (separate product). | Best for production self-hosted deployments needing built-in auth, personal-data controls, and project-scoped API keys in the OSS version. MIT licence. | Best for teams prioritising low setup friction and production alerting on cloud. Opik Cloud appears to offer the broadest alerting surface of the verified sources (Slack, PagerDuty, webhooks). Self-hosted OSS has no auth but zero-credential setup. Apache 2.0. |

---

## Key findings

1. **In the verified sources, Phoenix is the most explicitly OpenTelemetry-oriented of the three.** It is the one most clearly using OTLP as its primary ingestion path, and the only one used here with standard W3C `traceparent` for distributed trace propagation — meaning sub-agent services in the A2A system required no Phoenix-specific code. Langfuse and Opik both expose OTLP endpoints but were integrated via their native SDK callbacks in this project, where they require tool-specific propagation headers on both sides.

2. **In the sources verified here, Langfuse is the one with the clearest built-in self-hosted authentication and personal-data controls.** Phoenix and Opik both ship with no login screen and no ingestion auth by default — securing them requires a reverse proxy or cloud IAP. Langfuse includes email/password login, social OAuth (Google, GitHub, Microsoft), project-scoped API key pairs, and personal-data masking controls (masking, deletion, retention), all in the free self-hosted edition.

3. **In this project, the same evaluation-metric gap remained across all three tools.** The `EvaluatorAgent` faithfulness, completeness, and guardrail compliance scores are computed in the LangGraph state but never written back to any observability backend. The Feedback/Scores tabs are empty across all three tools. Small post-step logging calls (`phoenix.score()`, `langfuse.score()`, `opik.log_feedback_score()`) after each evaluation step would close this gap — it is the single highest-impact improvement available without changing the instrumentation strategy.

4. **A2A trace structure quality differs significantly.** Phoenix and Opik both produce 1 unified trace per query in the A2A session (5 traces for 5 queries), with all sub-agent spans nested under a single root. Langfuse produces 19 separate traces for the same session — one per LangGraph node execution — requiring the session view to re-assemble the full picture. For debugging distributed agent behaviour, Phoenix and Opik are meaningfully more convenient than Langfuse in A2A mode.

5. **Prompt management, LLM-as-Judge, datasets, experimentation, and community are a shared baseline — not differentiators.** All three tools offer prompt versioning, an interactive playground, LLM-as-Judge evaluation pipelines, human annotation queues, and dataset-based systematic testing. All three have active open-source repositories backed by commercial companies. These capabilities should be treated as table stakes when selecting a tool; the decision criteria lie in instrumentation model, authentication, alerting, and OTel standards compliance — the dimensions where the tools diverge.

6. **Per-call callback injection is a shared instrumentation risk for Langfuse and Opik.** Both tools require `model.invoke()` to carry an explicit callback handler. Any call made without the callback produces no trace entry — there is no global patch catching missed calls. Phoenix's `LangChainInstrumentor` eliminates this risk entirely by patching all LangChain calls at the process level. In practice this means adding a new LLM call to the codebase is safe with Phoenix, but requires explicit wiring with Langfuse and Opik.

---

## Final recommendation

No single tool is the clear winner across all dimensions — the right choice depends on deployment scope, security posture, and whether OTel standards interoperability is a priority.

**For a research or development environment** (this project's scope): **Phoenix** is the most ergonomic choice. Single container, zero credentials, automatic instrumentation, and standard W3C A2A propagation make it the fastest path from zero to a working distributed trace. The ELv2 licence is not a constraint for non-commercial research use.

**For a production self-hosted deployment**: **Langfuse** is the strongest option among those evaluated. In the sources verified here, it is the one with the clearest built-in UI authentication, personal-data masking controls, and project-scoped API keys in the self-hosted OSS edition — reducing the infrastructure overhead of securing the dashboard in a team environment. The async ClickHouse ingestion pipeline is designed for production trace volumes.

**For teams prioritising low setup friction and cloud alerting**: **Opik** (Cloud or self-hosted) offers the lowest credential friction for local use and, based on the sources verified here, the broadest alerting surface on cloud (Slack, PagerDuty, webhooks, 10 trigger event types). The Apache 2.0 licence and documented cloud/self-host parity make it a viable long-term choice.

**For this project specifically**, Phoenix was the most straightforward to work with during experimentation — auto-instrumentation eliminated per-call wiring risk, and W3C propagation kept the A2A implementation clean. For a production handoff of the same system, Langfuse would be the recommendation given its authentication and PII masking capabilities.
