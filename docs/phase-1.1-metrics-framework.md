# Core Metrics Framework

1. [Reasoning Traceability](./phase-1.0-observability-requirements.md) — see the "1. Reasoning Traceability" section in
   that file.

| Metric                     | Description                                                    | Purpose                              | Data Granularity | Evaluation Criteria     |
|----------------------------|----------------------------------------------------------------|--------------------------------------|------------------|-------------------------|
| Context Window Utilization | % of token limit used per reasoning step/cycle                 | Detect truncation, optimize prompts  | Per-step         | Native metric? Custom?  |
| Reasoning Depth            | Steps per reasoning cycle (plan → tool → reflect → repeat)     | Identify loops, overthinking         | Per-cycle        | Auto-counted?           |
| Full Sequence Logs         | Complete input/output history with timestamps                  | Reproducibility, root cause analysis | Session-level    | Searchable? Exportable? |
| Tool Calls                 | Input params, output results, latency per tool invocation      | Decision quality, perf bottlenecks   | Per-invocation   | Structured spans?       |
| Events                     | Context updates, tool invocations, trace branching points      | State evolution visibility           | Per-event        | Timeline view?          |
| Faithfulness/Groundedness  | % of reasoning steps supported by context (anti-hallucination) | Reasoning validity                   | Per-step         | Automated eval?         |

2. [Multi-Agent Coordination](./phase-1.0-observability-requirements.md) — see the "2. Multi-Agent Coordination" section
   in that file.

## Multi-Agent Coordination Metrics Framework

| **Metric**                   | **Description**                                                  | **Evaluation Criteria**                           |
|------------------------------|------------------------------------------------------------------|---------------------------------------------------|
| **Inter-Agent Messages**     | Message content, protocol, context, and timing between agents    | Structured spans capture payloads + metadata?     |
| **Communication Efficiency** | Tasks completed per message/token exchanged                      | Auto-calculated ratio or derivable from traces?   |
| **Message Redundancy**       | Semantic similarity across inter-agent communications            | Embedding distance or duplicate detection?        |
| **Shared State Consistency** | Versioning, conflict detection, and data integrity across agents | Immutable snapshots + conflict resolution logs?   |
| **State Sync Latency**       | Time between state updates across distributed agents             | Span timing correlation across agent instances?   |
| **State Divergence Rate**    | Frequency of inconsistent states between agents                  | Automated consistency checks in traces?           |
| **Aggregate Throughput**     | Tasks completed per hour across all agent instances              | Session-level dashboard with capacity metrics?    |
| **Agent Utilization**        | % time idle vs working across agent pool                         | Resource metrics per agent instance?              |
| **Coordination Overhead**    | % time spent communicating vs executing tasks                    | Communication vs execution time breakdown?        |
| **Decision Alignment**       | % synchronized actions vs independent decisions                  | Action correlation analysis across agents?        |
| **Conflict Resolution Rate** | Success rate of resolving state/action conflicts                 | Conflict events with resolution outcomes?         |
| **Coordination Fidelity**    | LLM-judged quality of agent collaboration and planning alignment | Native evaluation framework for team performance? |

3. [Governance and Guardrails](./phase-1.0-observability-requirements.md) — see the "3. Governance and Guardrails"
   section in
   that file.

## Governance and Guardrails Metrics Framework

| **Metric**                     | **Description**                                                             | **Evaluation Criteria**                           |
|--------------------------------|-----------------------------------------------------------------------------|---------------------------------------------------|
| **Policy Enforcement**         | Log enforcement events, detected violations, response actions, outcomes     | Structured violation spans with remediation logs? |
| **Data Retention Compliance**  | PII anonymization status, retention period adherence, access control audits | Automated PII detection + retention timers?       |
| **Sensitive Data Exposure**    | Detection of emails, credentials, API keys in logs/traces/reasoning         | Regex/pattern matching + alerting on exposure?    |
| **Guardrail Violations**       | Prompt injection attempts, unsafe computations, disallowed actions          | Semantic analysis + blocking rules triggered?     |
| **Violation Precision/Recall** | True positives (blocked harms) vs false negatives (missed harms)            | TP/FP/FN/TN tracking with F1 score computation?*  |

### TP/TN/FP/FN

In the context of guardrail violation detection, the TP/TN/FP/FN measure how well your policy enforcement system
identifies actual violations:

| Term                | Meaning                          | Guardrail Example                   |
|---------------------|----------------------------------|-------------------------------------|
| TP (True Positive)  | Correctly flagged as violation   | Detected prompt injection → blocked |
| TN (True Negative)  | Correctly allowed (no violation) | Normal query → allowed              |
| FP (False Positive) | Wrongly flagged as violation     | Benign input → falsely blocked      |
| FN (False Negative) | Missed actual violation          | Malicious prompt → allowed          |

Why It Matters for Governance?

Precision, Recall and F1 are standard measures for classifier/alert quality. Use LaTeX display math so they render
cleanly in MathJax/KaTeX-capable viewers.

Precision (fraction of flagged/blocked actions that were actually harmful):

$$
\mathrm{Precision} = \frac{TP}{TP + FP}
$$

As a percentage:

$$
\mathrm{Precision}\% = \frac{TP}{TP + FP} \times 100\%
$$

Recall (fraction of actual harmful actions that were detected):

$$
\mathrm{Recall} = \frac{TP}{TP + FN}
$$

As a percentage:

$$
\mathrm{Recall}\% = \frac{TP}{TP + FN} \times 100\%
$$

F1 score (harmonic mean of precision and recall):

$$
F_1 = 2 \cdot \frac{\mathrm{Precision} \cdot \mathrm{Recall}}{\mathrm{Precision} + \mathrm{Recall}} = \frac{2\,TP}{2\,TP + FP + FN}
$$

Edge cases and reporting guidance:

- If a denominator (e.g. $TP+FP$ or $TP+FN$) equals zero, the ratio is undefined; report the metric as "N/A" and include
  the raw counts (TP/FP/FN) so readers can interpret the result.

Numeric example:

- TP = 80, FP = 20, FN = 10
    - Precision = $\dfrac{80}{80+20} = 0.80$ → Precision% = $80\%$
    - Recall = $\dfrac{80}{80+10} \approx 0.8889$ → Recall% ≈ $88.89\%$
    - F1 = $\dfrac{2\times 80}{2\times 80 + 20 + 10} \approx 0.8419$ → F1 ≈ $84.19\%$


4. [Performance Metrics](./phase-1.0-observability-requirements.md) — see the "4. Performance Metrics" section in that
   file.

| Metric               | Description                           | Evaluation Criteria                    |
|----------------------|---------------------------------------|----------------------------------------|
| End-to-End Latency   | Time from request to final response   | P95/P99 percentiles across sessions?   |
| Token Usage/Cost     | Total input+output tokens per task    | Provider breakdown + cost attribution? |
| Error Rate           | % failed tasks (exceptions, timeouts) | Structured error classification?       |
| Concurrency Capacity | Max simultaneous agent instances      | Load testing + saturation points?      |
| Cache Hit Rate       | % repeated computations avoided       | Semantic deduplication tracking?       |

### What Are Percentiles?

Percentiles are statistical measures that indicate the value below which a given percentage of observations in a dataset
fall.
While an average (mean) tells you how the system performs for the "typical" user, percentiles reveal how it performs for
the users experiencing the most friction or lag.

* **P95 (95th Percentile)**: This is the value below which 95% of all sessions fall. In other words, only 5% of your
  agent
  sessions are slower than this value. It represents the experience of your "frustrated" users.

* **P99 (99th Percentile)**: This is the value below which 99% of all sessions fall. Only 1% of sessions are slower than
  this.
  This is often referred to as "tail latency" and represents the "worst-case" scenarios—such as a session hitting a
  massive loop, a tool timeout, or a token explosion.

5. [Quality Metrics](./phase-1.0-observability-requirements.md) — see the "5. Quality Metrics" section in that file.

| Metric            | Description                      | Evaluation Criteria                      |
|-------------------|----------------------------------|------------------------------------------|
| Task Success Rate | % tasks completed successfully   | Automated success criteria + human eval? |
| Output Accuracy   | Correctness vs ground truth      | LLM-as-judge or dataset evals?           |
| User Satisfaction | CSAT scores from human feedback  | Session-level thumbs up/down capture?    |
| Completeness      | % required information provided  | Checklist validation per task type?      |
| Actionability     | % outputs leading to user action | Click-through or follow-up rates?        |

* CSAT scores (Customer Satisfaction Score) measure how happy users are with specific agent interactions using simple
  post-task surveys.

6. [Safety Metrics](./phase-1.0-observability-requirements.md) — see the "6. Safety Metrics" section in that file.

# What Drift Detection should cover in an agent context?

| Drift Type      | What Changes                           | Impact on Agents       | Detection Method                          |
|-----------------|----------------------------------------|------------------------|-------------------------------------------|
| Data Drift      | Input distributions (prompts, context) | Poor reasoning quality | Statistical tests (KS, PSI) on embeddings |
| Concept Drift   | Task semantics/expected outputs        | Task success drops     | Output quality metrics vs baseline        |
| Model Drift     | Underlying LLM performance             | Reasoning degrades     | Token usage + latency anomalies           |
| Behavior Drift  | Agent decision patterns                | Coordination fails     | Step count, tool call distributions       |
| Sentiment Drift | Agent tone/personality changes         | User dissatisfaction   | LLM-evaluated sentiment scores            |




# Retention, privacy, and security requirements for observability data

There are different types of observability data (metrics, logs, traces) and each has its own retention, privacy, and security requirements. 

Swiss Data Protection Act (DPA) and the General Data Protection Regulation (GDPR) in the European Union are two key regulations that govern data privacy and security.
Based on the industry best practices and regulatory requirements, there might be different retention periods for different types of observability data. 
For example, metrics might be retained for 90 days, logs for 30 days, and traces for 7 days.
