# Open-Source Tools for AI Agent Observability

## Tool selection

Three open-source platforms were selected for detailed evaluation based on their active development, LangChain support, and ability to run fully locally:

1. **Arize Phoenix** — https://github.com/Arize-ai/phoenix
2. **Langfuse** — https://github.com/langfuse/langfuse
3. **Comet Opik** — https://github.com/comet-ml/opik

Each tool was evaluated across the same three-pillar framework and the same set of experiment runs, so the results are directly comparable.

---

## High-level comparison

The table below summarises the key characteristics of the three tools based on an independent review [CITE-TRILOGY-COMPARISON]. The values have not all been independently verified in this project — they serve as a starting point for understanding the positioning of each tool before the detailed evaluation.

| Tool | Tracing depth | Evaluation strength | Performance | Best fit | Main drawback |
|---|---|---|---|---|---|
| Arize Phoenix | High (OTel native) | Fixed metrics, RAG focus | Medium | ML experimentation, debugging | Fewer prompt management features |
| Langfuse | High | Flexible LLM-judge, feedback loops | High (ClickHouse backend) | Production, cost tracking, team collaboration | UI-heavy for solo developers |
| Comet Opik | High (nested traces) | Custom evaluators, guardrails | Very high | Rapid iteration, CI/CD, agent tuning | More code-first, lighter UI |

The detailed per-tool evaluations based on actual experiment runs are in:
1. [Arize Phoenix](./phase-2.1.1-arize-phoenix-evaluation.md)
2. [Langfuse](./phase-2.1.2-langfuse-evaluation.md)
3. [Comet Opik](./phase-2.1.3-comet-opik-evaluation.md)

---

## Three-pillar evaluation framework

All three tools are evaluated using the same three-pillar framework. This structure was chosen because it separates concerns that are often conflated: how you connect the tool to your agent, what the tool actually shows you, and what it costs to run it in practice.

### Pillar 1: Integration and Instrumentation Capabilities (The "How")

This pillar covers how the tool connects to the agent and what instrumentation is required.

| Evaluation category | Criteria | Why it matters |
|---|---|---|
| Native libraries | Support for Python/TypeScript SDKs and popular agent frameworks (LangChain, CrewAI, Google ADK) | Reduces integration effort and avoids custom glue code |
| Ingestion formats | Support for OpenInference and OpenTelemetry (OTel) standards | Ensures vendor-neutrality and avoids lock-in to a single observability backend |
| Auto-instrumentation | Ability to capture agent spans, tool calls, and model parameters without manual decorators on every call | Critical for capturing the full reasoning chain without missing steps |
| Data exporters | API/SDK access, JSON/CSV exports, or scheduled exports | Required for offline analysis and data portability |

### Pillar 2: Capabilities (The "What")

This pillar covers what the tool can show you once traces are ingested. The specific metrics tracked are defined in [Phase 1](./phase-1.0-observability-requirements.md) and include: span hierarchy, token usage, cost attribution, session grouping, LLM-as-judge evaluation scores, guard trigger visibility, and cross-process correlation.

### Pillar 3: Operational Considerations (The "Cost")

This pillar covers what it takes to run the tool in practice — setup, resource usage, and long-term sustainability.

| Evaluation category | Criteria | Why it matters |
|---|---|---|
| License | Distinguish between MIT/Apache 2.0 and open-core (enterprise license keys required) | MIT (Langfuse) offers full feature parity for self-hosting; ELv2 (Phoenix) restricts some commercial use |
| Deployment model | Local/Docker support vs. cloud SaaS only | Self-hosting is often required for data residency requirements (GDPR, Swiss DPA) |
| Performance overhead | Ingestion latency and impact on the agent's end-to-end response time | High-volume deployments need low-overhead backends |
| Resource usage | Hardware requirements (PostgreSQL, ClickHouse, SQLite) | Determines whether the tool can run on a developer laptop or requires a dedicated server |

---

## A2A protocol observability requirement

The Agent2Agent (A2A) protocol explicitly defines observability as an enterprise-readiness requirement. It mandates OTel-based distributed tracing across HTTP boundaries:

> **A2A Clients and Servers *should* participate in distributed tracing systems**,
> adopting OpenTelemetry and W3C Trace Context headers for end-to-end visibility.
>
> Reference: [A2A Enterprise-Ready — Tracing, Observability and Monitoring](https://a2a-protocol.org/latest/topics/enterprise-ready/#tracing-observability-and-monitoring)

This directly validates the implementation approach taken in `src/multi_agent_a2a/`: W3C `traceparent` links spans across the three processes, W3C `baggage` carries `session.id`, and all three processes connect to the same OTel-compatible backend (Phoenix, Langfuse, or Opik). See `src/multi_agent_a2a/README.md` for the full mapping from protocol spec to implementation.

---

## Alternative: Python-native logging

A simpler alternative to OTel-based tools is to use Python's standard `logging` module directly, routing all agent events through a centralised logger. AG2 (formerly AutoGen) documents this pattern:

> **AG2 Event Logging & Observability**
> https://docs.ag2.ai/latest/docs/blog/2025/12/23/Ag2-logging-events/#basic-setup

The table below maps the AG2 logging patterns to the equivalent constructs in this project:

| AG2 pattern | Equivalent in this project |
|---|---|
| Centralised `ag2.event.processor` logger | Per-module `logging.getLogger(...)` in each agent |
| Events captured: init, messages, tool calls, termination | `TraceEvent` entries in `AgentState.trace_events` (reconstructable without a backend) |
| JSON formatter for structured output | Standard text format; `LOG_LEVEL` env var controls verbosity |
| `RotatingFileHandler` for production | Not implemented — OTel-based exporters (Phoenix, Langfuse, Opik) serve this role |
| Testing: capture events to `StringIO` | Tests inject fake agents/models; `TraceEvent` list verified in assertions |

**Why OTel-based tools were preferred over pure logging for this project:**
- Distributed trace correlation across the three A2A processes requires OTel (W3C `traceparent` / `baggage`)
- Session grouping, span hierarchies, and LLM cost metrics are built into Phoenix, Langfuse, and Opik
- Python logging alone cannot link spans across process boundaries without additional infrastructure

---

## References

| Citation key | Source |
|---|---|
| [CITE-TRILOGY-COMPARISON] | Trilogy AI. (2025). *LLM Evaluation Frameworks — Comparison of Phoenix, Langfuse, and Opik*. https://trilogyai.substack.com/p/llm-evaluation-frameworks |
