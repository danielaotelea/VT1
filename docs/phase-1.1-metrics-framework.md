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
* **Precision** = TP/(TP+FP): % of blocked actions that were actually harmful
* **Recall** = TP/(TP+FN): % of actual violations that were caught
* **F1 Score** = 2×(Precision×Recall)/(Precision+Recall): Balances both
