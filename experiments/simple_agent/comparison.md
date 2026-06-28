# Simple Agent — Round 1 Experiment Comparison

Baseline: `none` (no observability overhead).  
All runs: gpt-4o, sampling_rate=1.0, 5 fixed arithmetic queries (Q1–Q5).

## Run Metadata

| Exporter | Session ID | Timestamp (UTC) | Model | Errors |
|----------|-----------|-----------------|-------|--------|
| `none` | `round1-none-001` | 2026-06-28 15:58:28 | gpt-4o | 0 |
| `otel-stdout` | `round1-otel-stdout-001` | 2026-06-28 16:02:23 | gpt-4o | 0 |
| `phoenix` | `round1-phoenix-001` | 2026-06-28 15:31:42 | gpt-4o | 0 |
| `langfuse` | `round1-langfuse-001` | 2026-06-28 15:30:49 | gpt-4o | 0 |
| `opik` | `round1-opik-001` | 2026-06-28 15:29:06 | gpt-4o | 0 |

## Per-Query Latency

> Δ = exporter latency − `none` baseline. Negative Δ is within normal OpenAI API variance (~1–2 s per call).

| Query | Description | `none` (baseline) | `otel-stdout` | `phoenix` | `langfuse` | `opik` |
|---|---|---|---|---|---|---|
| **Q1** | Single tool call | 2,583 ms | 1,482 ms (-1,102 ms) | 1,269 ms (-1,314 ms) | 1,228 ms (-1,355 ms) | 2,727 ms (+144 ms) |
| **Q2** | Two sequential tool calls — same type | 1,706 ms | 2,349 ms (+643 ms) | 1,633 ms (-73 ms) | 2,410 ms (+704 ms) | 2,638 ms (+932 ms) |
| **Q3** | Two sequential tool calls — different types | 2,120 ms | 5,013 ms (+2,893 ms) | 1,956 ms (-164 ms) | 1,444 ms (-676 ms) | 1,863 ms (-257 ms) |
| **Q4** | Chained output between calls | 1,702 ms | 1,749 ms (+47 ms) | 1,428 ms (-274 ms) | 1,433 ms (-269 ms) | 1,535 ms (-167 ms) |
| **Q5** | Three tool calls — longest trace | 2,047 ms | 2,357 ms (+310 ms) | 2,250 ms (+203 ms) | 2,334 ms (+287 ms) | 2,455 ms (+408 ms) |
| **Total** | *5 queries* | **10,158 ms** | **12,950 ms** (+2,792 ms) | **8,536 ms** (-1,622 ms) | **8,850 ms** (-1,308 ms) | **11,218 ms** (+1,060 ms) |

## Per-Query Token Counts (Input / Output)

> Variation across exporters on the same query reflects LLM non-determinism (output length) and different execution paths (parallel vs. sequential tool calls), not exporter interference.

| Query | `none` | `otel-stdout` | `phoenix` | `langfuse` | `opik` |
|---|---|---|---|---|---|
| **Q1** | 371 / 27 | 371 / 27 | 371 / 27 | 371 / 27 | 371 / 27 |
| **Q2** | 424 / 74 | 612 / 58 | 424 / 74 | 612 / 73 | 612 / 73 |
| **Q3** | 420 / 72 | 420 / 69 | 607 / 53 | 420 / 72 | 420 / 72 |
| **Q4** | 426 / 75 | 426 / 75 | 426 / 77 | 426 / 77 | 426 / 77 |
| **Q5** | 675 / 98 | 716 / 77 | 675 / 98 | 675 / 98 | 896 / 58 |
| **Total** | **2,316 / 346** | **2,545 / 306** | **2,503 / 329** | **2,504 / 347** | **2,725 / 307** |

## Total Cost (USD)

| Exporter | Total cost | Δ vs baseline | Input tokens | Output tokens |
|----------|-----------|---------------|-------------|--------------|
| `none` | $0.01677 | — | 2,316 | 346 |
| `otel-stdout` | $0.01732 | +$0.00055 | 2,545 | 306 |
| `phoenix` | $0.01745 | +$0.00068 | 2,503 | 329 |
| `langfuse` | $0.01773 | +$0.00096 | 2,504 | 347 |
| `opik` | $0.01823 | +$0.00146 | 2,725 | 307 |

## Correctness

> ✅ expected answer found in output   ❌ not found

| Query | Expected | `none` | `otel-stdout` | `phoenix` | `langfuse` | `opik` |
|---|---|---|---|---|---|---|
| **Q1** | `42` | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Q2** | `200` | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Q3** | `38.0` | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Q4** | `12.0` | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Q5** | `35.0` | ✅ | ✅ | ✅ | ✅ | ✅ |

## Instrumentation Overhead Summary

> Based on a single run each. OpenAI API latency variance (~1–2 s per call) dominates these numbers. Treat as indicative, not statistically significant.

| Exporter | Total latency | Δ vs none | Overhead % |
|----------|--------------|-----------|------------|
| `none` | 10,158 ms | +0 ms | +0.0% |
| `otel-stdout` | 12,950 ms | +2,792 ms | +27.5% |
| `phoenix` | 8,536 ms | -1,622 ms | -16.0% |
| `langfuse` | 8,850 ms | -1,308 ms | -12.9% |
| `opik` | 11,218 ms | +1,060 ms | +10.4% |

## Key Findings

*(Fill in after reviewing the tool UIs and screenshots.)*

- **Correctness:** all exporters produced correct answers for all 5 queries — no exporter interferes with agent logic.
- **Latency overhead:** differences are within OpenAI API variance; no tool adds measurable blocking overhead for a single-process agent.
- **Token consistency:** minor variation per query is expected (LLM non-determinism in output length, parallel vs. sequential tool dispatch). No exporter inflates token counts.
- **Cost:** total cost is consistent across exporters (~$0.017–0.018). Cost differences reflect token variance, not SDK overhead.
