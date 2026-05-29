# Simple Agent — Round 1 Experiment Results

Populated during Milestone 3 (tool evaluation Round 1).

Each session is run with `experiments/simple_agent/run_experiment.py`.
Raw JSON results are saved in `runs/<session-id>.json`.

---

## Standard Query Set

| ID | Description | Prompt | Expected answer |
|----|-------------|--------|-----------------|
| Q1 | Single tool call | What is 6 multiplied by 7? | 42 |
| Q2 | Two sequential calls — same type | Add 27 and 73, then multiply the result by 2. | 200 |
| Q3 | Two sequential calls — different types | Divide 100 by 4, then add 13. | 38.0 |
| Q4 | Chained output between calls | Multiply 8 by 9, then divide the result by 6. | 12.0 |
| Q5 | Three tool calls — longest trace | What is 15 divided by 3? Then multiply that by 5. Then add 10. | 35.0 |

---

## Run Log

| Session ID | Tool | Date | Q1 ms | Q2 ms | Q3 ms | Q4 ms | Q5 ms | Total tokens | Total cost (USD) | Errors |
|------------|------|------|-------|-------|-------|-------|-------|-------------|-----------------|--------|
| _(to be filled)_ | | | | | | | | | | |

---

## Arize Phoenix — Observations

*(Fill after ≥5 sessions with `--exporter phoenix`)*

### Trace capture
- [ ] All 5 queries produced a trace in the Phoenix UI
- [ ] LLM spans present with correct `gen_ai.request.model` attribute
- [ ] Tool call spans present (add / multiply / divide)
- [ ] `session.id` visible on spans — traces grouped under session view
- [ ] `service.name` / `service.version` visible in Resource attributes panel
- [ ] `gen_ai.usage.input_tokens` / `output_tokens` visible on LLM spans
- [ ] `cost.usd` visible as a span attribute

### Dashboard / UI capability
- [ ] Session-level latency aggregation available
- [ ] Per-span latency timeline visible
- [ ] Token usage chart available
- [ ] Cost attribution visible

### Qualitative notes

---

## Langfuse — Observations

*(Fill after ≥5 sessions with `--exporter langfuse`)*

### Trace capture
- [ ] All 5 queries produced a trace in the Langfuse UI
- [ ] LLM spans present with model name
- [ ] Tool call spans present
- [ ] `session_id` visible — traces grouped under session view
- [ ] Token counts visible on LLM spans (from LangChain callback)
- [ ] Cost visible (Langfuse native cost field)

### Dashboard / UI capability
- [ ] Session-level view available
- [ ] Per-trace latency breakdown visible
- [ ] Token usage aggregation available
- [ ] Cost dashboard available

### Qualitative notes

---

## Comet Opik — Observations

*(Fill after ≥5 sessions with `--exporter opik`)*

### Trace capture
- [ ] All 5 queries produced a trace in the Opik UI
- [ ] LLM spans present with model name
- [ ] Tool call spans present
- [ ] `session_id` visible as metadata — traces searchable by session
- [ ] Token counts visible on LLM spans

### Dashboard / UI capability
- [ ] Session metadata searchable / filterable
- [ ] Per-trace latency breakdown visible
- [ ] Token usage visible

### Qualitative notes
