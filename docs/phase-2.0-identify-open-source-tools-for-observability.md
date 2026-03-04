# Open Source tools for observability of AI agents

## Propose a shortlist of candidate tools for prototyping:

1. Arize Phonex: https://github.com/Arize-ai/phoenix
2. Langfuse: https://github.com/langfuse/langfuse
3. Comet Opik: https://github.com/comet-ml/opik

Short comparison of the tools:
https://trilogyai.substack.com/p/llm-evaluation-frameworks

| Tool          | Tracing depth | Evals strength               | Speed/perf             | Best agent fit                          | Drawback                   |
|---------------|---------------|------------------------------|------------------------|-----------------------------------------|----------------------------|
| Arize Phoenix | High (OTEL)   | Fixed metrics, RAG focus     | Medium                 | ML experimentation                      | Slower evals, less prompts |
| Langfuse      | High          | Flexible LLM-judge, feedback | High (ClickHouse)      | Prod collab, costs, sessions            | UI-heavy for solo devs     |
| Comet Opik    | High (nested) | Custom auto, guardrails      | Very high (~7x faster) | Rapid iter/CI, agent tuning datatalks+2 | Code-first (less UI)       |

## Three-pillar framework

In order to evaluate the tools, we can use a three-pillar framework:

1. **Pillar 1: Integration and Instrumentation Capabilities (The "How")**

| Evaluation Category  | Evaluation Criteria                                                                                       | Why it Matters                                                                         |
|----------------------|-----------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| Native Libraries     | Support for Python/TS SDKs and popular 2026 agent frameworks (e.g., LangChain, CrewAI, Google ADK).       | High ease-of-integration minimizes code bloat and developer overhead.                  |
| Ingestion Formats    | Support for OpenInference and OpenTelemetry (OTEL) standards.                                             | Ensures vendor-neutrality and future-proofing of your "Agent Telemetry" layer.         |
| Auto-Instrumentation | Ability to automatically capture agent spans, tool calls, and model parameters without manual decorators. | Crucial for capturing Reasoning Depth and Tool Calls accurately without missing steps. |
| Data Exporters       | Availability of API/SDK access, JSON/CSV exports, or scheduled exports to S3/Data Lakes.                  | Required for offline analysis, fine-tuning, and meeting "Swiss DPA" data portability.  |

2. **Pillar 2: Capabilities (the "What")**

Based on the metrics defined in [Phase 1](./phase-1.0-observability-requirements.md)

3. **Pillar 3: Operational Considerations and  (the "Cost")**

Understand the long term sustainability of the tool in production, including costs, data retention, and security.

| Evaluation Category  | Evaluation Criteria                                                            | Why it Matters                                                                               |
|----------------------|--------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| License Constraints  | Distinguish between MIT/Apache 2.0 and "Open Core" features (EE license keys). | MIT (Langfuse) offers full feature parity for self-hosting.                                  |
| Deployment Model     | Local/Docker support vs. Cloud SaaS.                                           | Self-hosting is often required for GDPR/Swiss DPA data residency.                            |
| Performance Overhead | Ingestion latency and impact on the agent's end-to-end response time.          | High-volume ingestion (e.g., Opik’s 40M traces/day) is critical for large-scale agent pools. |
| Resource Usage       | Hardware requirements (e.g., PostgreSQL for state, ClickHouse for analytics).  | Production-ready setups often require 2+ CPU cores and 3 GB+ RAM per container.              |


For the selected tools, the evaluation based on the three-pillar framework is documented in a comparative analysis report.
1. [Arize Phoenix](./phase-2.1.1-arize-phoenix-evaluation.md)
2. [Langfuse](./phase-2.1.2-langfuse-evaluation.md)
3. [Comet Opik](./phase-2.1.3-comet-opik-evaluation.md)
