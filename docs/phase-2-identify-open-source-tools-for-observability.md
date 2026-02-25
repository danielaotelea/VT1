# Open Source tools for observability of AI agents

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
