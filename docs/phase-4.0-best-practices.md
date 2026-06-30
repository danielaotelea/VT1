# Best Practices for AI Agent Observability

Building observability for AI agents requires a fundamental shift from traditional system monitoring. Because agents are probabilistic and non-deterministic, capable of dynamically changing their tool usage and reasoning paths, flat logs and basic health metrics such as CPU utilisation or request latency are no longer sufficient to diagnose failures.

The following practices are derived from two sources: a online articles and reviews of the AI observability landscape, and the implementation and experimental findings of this project, which evaluated three tools (Arize Phoenix, Langfuse, and Comet Opik) against a single-agent ReAct system and a multi-agent A2A distributed pipeline. Implementation references point to `src/` in the accompanying repository.

---

## 1. Implement End-to-End Traces with Hierarchical Spans

To understand *why* an agent failed, you must be able to reconstruct its exact causal chain of decisions.

* **Span-per-tick tracing.** Every discrete reasoning step must generate a distinct span within a distributed trace. These should nest as hierarchical spans under a single parent trace for the full workflow.
* **Capture every layer.** Spans must individually record LLM calls (input and output tokens, temperature, model name), tool invocations (arguments, outputs, duration), memory operations (reads, writes, cache hits - not covered in this project implementation), and agent-to-agent handoffs.
* **Enable trace replay.** By capturing detailed execution flows hierarchically, you can pinpoint the exact sub-agent or tool step where a hallucination or failure originated, rather than only knowing that the overall pipeline failed.
* **Maintain a backend-independent audit trail.** In addition to emitting spans to an external backend, design agents to append structured event records to their own state as they execute. This gives a full audit trail reconstructable from the state object alone — useful for debugging, testing, and scenarios where no tracing backend is connected. The `AgentState.trace_events` pattern in `src/multi_agent/state.py` demonstrates this approach: every agent appends `TraceEvent` entries (timestamp, agent role, event type, payload) throughout execution, so the complete multi-agent trace is recoverable from state even when the observability backend is `none`.

---

## 2. Adopt Standardised Semantic Conventions

The fragmented landscape of AI frameworks makes vendor lock-in a significant operational risk. Standardisation ensures your traces can be ingested and correlated across any backend.

* **Use OpenTelemetry (OTel).** Adopt the emerging OTel GenAI semantic conventions (attributes such as `gen_ai.agent.name`, `gen_ai.agent.operation.name`, `gen_ai.usage.input_tokens`). These are not yet natively consumed by all evaluated tools, but they establish the portable baseline against which future tools will be built.
* **Emit both OTel GenAI and OpenInference token attributes.** Until convergence is reached, write `gen_ai.usage.input_tokens` (OTel semconv) and `llm.token_count.prompt` (OpenInference) on every LLM span. Phoenix reads the latter; future OTel-native tools will read the former. A single shared helper function handles this with negligible overhead — see `set_token_cost_attributes()` in `src/otel_utils.py`.
* **Set OTel Resource attributes explicitly.** Most tool SDKs do not infer `service.name`, `service.version`, or `deployment.environment` from the runtime. Pass a `Resource` object to the tracer provider at initialisation. In Phoenix, use `from phoenix.otel import Resource` and pass it to `register()`. Without explicit resource attributes, all spans appear under a generic unnamed service in the UI, making multi-service deployments impossible to navigate.
* **Prefer external over baked-in instrumentation.** While some frameworks offer built-in observability, the recommended approach is to use external OpenTelemetry instrumentation libraries. This decouples observability from your core framework and maintains alignment with industry standards as both evolve independently.

---

## 3. Enforce Strict Structure and Rich Metadata

Without high-cardinality metadata, finding the root cause of an issue across thousands of agent runs is practically impossible.

* **Tag from day one.** Inject structured metadata: `user_id`, `session_id`, `agent_role`, `strategy_id` into every span at initialization. Do not wait for a production incident to realise you need this context to filter failing traces. Retrofitting session tagging into a running system is significantly more costly than building it in from the start.
* **Structured logging.** Ensure logs capture the semantic context of operations in structured formats such as JSON. This includes storing full input artifacts, tool input/output pairs, and model decisions, so that log entries link directly to the corresponding spans in the tracing backend.
* **Pass session IDs at call time, not at startup.** For callback-based tools (Langfuse, Opik), the session ID must be injected into each individual framework call rather than configured once globally. Pass `adapter.callback(session_id=session_id)` to `agent.run()` on every call. A session ID set at startup will not propagate correctly to spans generated during individual requests.

---

## 4. Track AI-Specific Metrics

Beyond standard system health, you must monitor the unique economics and behavioural characteristics of large language models.

* **Span-level token tracking.** Because AI providers charge by the token, an inefficient retrieval step trapped in a loop can drain budgets rapidly. Track token consumption per request, per tool, and cumulatively to detect costs and unoptimized prompts.
* **Tool interaction metrics.** Monitor the success rates, external API latencies, and selection patterns of the tools your agent chooses to invoke. Repeated selection of the same tool is a reliable signal of loop behavior before the loop guard triggers.
* **Reasoning and quality signals.** Capture the intermediate reasoning steps of the agent and track qualitative indicators such as hallucination rates, factual consistency scores, and task completion alignment. Faithfulness scores from an LLM-as-judge step are a practical proxy for output quality in research-oriented agents.

---

## 5. Handle Cross-Process Session Propagation

Session correlation is straightforward in single-process systems. In distributed agent architectures — A2A services, microservices, serverless functions — it requires explicit engineering.

* **Understand the ContextVar boundary.** OpenInference's `using_session()` stores `session.id` in a local Python `ContextVar`. That variable never crosses a process boundary. If you rely on it alone in a system with multiple processes, each sub-agent service will produce spans with no session context, making the session view in the observability backend empty or fragmented.
* **Promote session.id into W3C Baggage before inter-service calls.** Before each outgoing HTTP call to a sub-agent service, read the current session ID and write it into W3C `baggage` via `set_baggage("session.id", value)`. Call `opentelemetry.propagate.inject(carrier)` to serialise both `traceparent` and `baggage` into the request headers. This couples session context to the distributed trace so both travel together.
* **Extract on the receiving side in middleware.** On each sub-agent service, mount an ASGI middleware that calls `opentelemetry.propagate.extract(request.headers)` to restore the OTel context (making sub-agent spans children of the orchestrator span), then reads `session.id` from the baggage header and applies it locally — via `using_session()` for Phoenix, or via `adapter.callback(session_id=...)` for Langfuse and Opik. The `TracingMiddleware` and per-tool `TracingStrategy` implementations in `src/multi_agent_a2a/` demonstrate this pattern.
* **Note the Opik difference.** Opik uses its own distributed trace headers (`opik_trace_id` / `opik_parent_span_id`) in addition to W3C `traceparent`. When Opik is active, populate these from `opik_context.get_distributed_trace_headers()` before each sub-agent call and extract them in middleware on the receiving side.

---

## 6. Match Your Instrumentation Model to Your Architecture

The choice between auto-instrumentation and per-call callback injection has significant consequences for trace completeness.

* **Auto-instrumentation (Phoenix via `LangChainInstrumentor`).** A single call at startup patches all LangChain operations at the process level. Every LLM call, tool invocation, and chain execution is covered automatically. Adding a new agent or LLM call to the codebase does not require any additional instrumentation wiring. This is the lowest-risk model for evolving codebases.
* **Per-call callback injection (Langfuse, Opik).** These tools require an explicit callback handler to be passed into each `model.invoke()` or `agent.run()` call. Any call made without the callback produces no trace entry — no error, no warning, simply a missing span. This is an operational risk: a new LLM call added by a developer who is unaware of the convention silently drops its trace. Mitigate this by centralising callback construction in a single factory function and enforcing its use through code review or a lint rule.
* **Instrument the synthesis step explicitly in A2A systems.** In distributed A2A orchestration, the orchestrator's own LLM call (the final synthesis step) is the only step covered by the orchestrator-side exporter. The researcher and evaluator services each initialise their own exporters independently. Verify that all three processes point to the same backend before sending a query — the `/health` endpoint pattern on each service, returning `{"exporter": "..."}`, makes this auditable at a glance.

---

## 7. Write Evaluation Scores Back to the Observability Backend

Computing a faithfulness or quality score within your agent and writing it as a span attribute is not the same as registering it with the observability platform's native scoring system.

* **Span attributes vs. native scores.** A faithfulness score stored as `span.set_attribute("faithfulness", 0.87)` is searchable in the spans tab but invisible to the platform's Feedback or Scores UI, and cannot trigger native alerting rules. The Feedback tabs in Phoenix, Langfuse, and Opik all remained empty during this project's experiment runs because scores were emitted only as span attributes.
* **Call the platform's scoring API after each evaluation step.** Add a short post-evaluation call following each LLM-as-judge response: `phoenix.score()`, `langfuse.score()`, or `opik.log_feedback_score()`. This registers the score as a first-class entity in the backend, enabling dashboard aggregation, time-series trending, and threshold-based alerting without additional configuration.
* **This is the single highest-impact improvement available** without changing the instrumentation strategy. It connects the agent's internal quality signal to the platform's operational visibility layer.

---

## 8. Design for Multi-Turn Sessions from the Start

Single-turn tracing is adequately handled by all three evaluated platforms. Production agents operate in multi-turn conversations where context persists across queries, and this creates three distinct concerns that are difficult to add retrospectively.

* **Externalize session state.** Move conversation history out of an in-memory dictionary into a durable store (Redis, a relational database) keyed by `session_id`, so sessions survive process restarts and horizontal scale-out. In-memory history is invisible to observability backends and incompatible with load-balanced deployments.
* **Track token usage per turn and its cumulative trend.** Context window overflow manifests as a gradual growth trend across turns, not as a spike in a single call. Track input token counts per turn so you can see the growth curve in the observability UI and alert before the context limit is hit.
* **Treat `session_id` as an operational primitive.** Every LLM call, tool invocation, cost record, and evaluation score should carry `session_id` from the very first turn, so the observability backend can answer "show me everything that happened in this conversation" rather than only "show me this one call". The session propagation infrastructure built for A2A v2 (§5 above) applies equally to multi-turn single-process deployments.

---

## 9. Use a Fixed Query Set for Reproducible Tool Evaluation

When comparing observability tools, the agent's LLM outputs introduce variability that can confound the comparison.

* **Run the same queries against every tool.** LLM output variability means a single-query evaluation cannot reliably distinguish tool capability from a lucky or unlucky model response. Use a fixed query set that covers the range of complexity you care about — simple single-turn queries for baseline latency, multi-step queries for tool call tracing, and adversarial or ambiguous queries for faithfulness and HITL guard evaluation.
* **Include a query type that triggers retry or escalation.** The experiment query set in this project intentionally includes a meta-comparative question ("How does Arize Phoenix compare to Langfuse?") that consistently triggered low faithfulness scores and HITL escalation across all three tools. This class of query is the most informative for evaluating how observability backends surface guard events.
* **Record session IDs and reproduce runs.** Store raw output JSON per session, not only aggregate metrics. The ability to reload and inspect a specific session's trace is essential when a tool difference is found — you need to correlate the JSON output with what the tool's UI actually showed.

---

## 10. Move to Continuous Evaluation and Governance

Observability should function as a proactive control harness, not only a reactive debugging tool.

* **LLM-as-judge in production.** Feed telemetry back into continuous evaluation loops. Run automated judges against sampled production traces to detect semantic drift or policy violations before users report them. The faithfulness and completeness scoring implemented in `src/multi_agent/evaluator.py` is a starting point; connecting its output to the platform's scoring API (§7) closes the loop.
* **Implement guardrails and monitor their activation rates.** For enterprise and regulated environments, monitor for PII leaks, toxicity, and restricted topics in real time. Pair guardrail events with kill switches and compliance export trails for unattended agents. Track the rate at which each guard fires — a rising HITL escalation rate across sessions is a signal that the query distribution has shifted or the evaluator's thresholds need recalibration.
* **Alert on trends, not only on individual events.** A single HITL escalation may be expected. A rising escalation rate over the past hour is an operational incident. Configure threshold-based alerts on aggregated metrics (escalation rate, average faithfulness, P95 latency) rather than on individual span events.

---

## Common Anti-Patterns

The following mistakes are frequently observed in production agent observability setups. Each silently degrades trace quality without raising an immediate error.

* **Generating a new `trace_id` in every service.**
Creating a fresh trace ID for each service in a distributed pipeline breaks the end-to-end trace into disconnected fragments. Each service appears as an independent trace with no parent, making it impossible to follow a user request across the system. Fix: propagate the `traceparent` header from the originating call and let the receiving service attach its spans as children of the incoming context.

* **Passing only `trace_id`, without span parent relations.**
Forwarding the trace ID without also forwarding `span_id` and the parent relationship results in a flat list of events rather than a hierarchical span tree. Without parent–child relations, the timing and causal nesting of steps (which tool call triggered which LLM call, which sub-agent was retried) are lost. Fix: use a standards-compliant propagator (W3C `traceparent`) that carries both the trace ID and the current span ID.

* **Dropping trace context in asynchronous queues.**
If task metadata in an asynchronous queue does not include the serialised trace context, downstream async steps fall outside the trace. This commonly masks cascading failures: the originating span appears to complete successfully, and the failure in the downstream step appears as an unrelated orphan. Fix: serialize the full OTel context (via `propagate.inject()`) into the queue message and extract it (`propagate.extract()`) on the consumer side before processing.

* **Omitting `service.name` and `operation.name`.**
Without these fields, a span records that something failed, but not which service or which operation was responsible. In a multi-agent system with a shared backend, this makes span search by service impossible. Fix: set `service.name` in the OTel `Resource` at tracer provider initialization and set `operation.name` on every span.

* **Relying on span attributes for evaluation score visibility.**
Writing a faithfulness score as a span attribute (`span.set_attribute("faithfulness", score)`) is not equivalent to registering it with the platform. The attribute is searchable in the span detail view but does not populate the Feedback or Scores tab, cannot trigger alerting rules, and is not included in aggregate quality dashboards. Fix: call the platform's scoring API explicitly after each LLM-as-judge response (§7).

* **Configuring session IDs once at startup for callback-based tools.**
For Langfuse and Opik, a session ID set once at application startup is not propagated to spans generated during individual requests. Each request creates spans with the startup session ID rather than its own. Fix: pass the session-specific callback to every `model.invoke()` or `agent.run()` call (§3, §5).
