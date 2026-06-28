#!/usr/bin/env python3
"""Multi-Agent System — Experiment Runner (Round 2).

Runs a fixed query set against the OrchestratorAgent with one observability
exporter, captures E2E latency, evaluation scores, retry behaviour, guard
triggers, and cost per query, then saves a JSON result file to
experiments/multi_agent/runs/.

Usage
-----
    # Run with Phoenix (must be running at PHOENIX_COLLECTOR_ENDPOINT)
    python experiments/multi_agent/run_experiment.py --exporter phoenix

    # Explicit session ID (used to group traces in the tool UI)
    python experiments/multi_agent/run_experiment.py --exporter langfuse --session-id round2-langfuse-001

    # Dry-run with no tracing (sanity check, no API key needed)
    python experiments/multi_agent/run_experiment.py --exporter none

Results are saved to:
    experiments/multi_agent/runs/<session-id>.json
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.multi_agent.config import MultiAgentConfig
from src.multi_agent.orchestrator import OrchestratorAgent

# ---------------------------------------------------------------------------
# Fixed query set — identical across all tools to enable fair comparison.
#
# Three query types are used (as required by M5: "≥3 query types"):
#   Type A — Focused factual: narrow, well-defined answer expected.
#             Tests single-pass Researcher → Evaluator with high faithfulness.
#   Type B — Comparative: requires synthesising multiple sources.
#             Tests multi-source citation and faithfulness scoring.
#   Type C — Multi-part: several sub-questions in one prompt.
#             Tests potential retry behaviour and HITL escalation.
# ---------------------------------------------------------------------------

QUERIES = [
    {
        "id": "Q1",
        "type": "A — Focused factual",
        "prompt": "What is OpenTelemetry and what problem does it solve for distributed systems?",
    },
    {
        "id": "Q2",
        "type": "A — Focused factual",
        "prompt": "What is the OpenInference semantic convention and how does it extend OpenTelemetry for LLM applications?",
    },
    {
        "id": "Q3",
        "type": "B — Comparative",
        "prompt": "How does Arize Phoenix compare to Langfuse for tracing LLM agent applications in 2025?",
    },
    {
        "id": "Q4",
        "type": "B — Comparative",
        "prompt": "What are the differences between callback-based and auto-instrumentation approaches for LLM observability?",
    },
    {
        "id": "Q5",
        "type": "C — Multi-part",
        "prompt": (
            "What are the main observability requirements for a multi-agent LLM system? "
            "Which open-source tools best address those requirements in 2025, "
            "and what are their key limitations?"
        ),
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_cost_from_events(trace_events: list) -> float:
    """Sum cost_usd from all llm_response and evaluation events."""
    total = 0.0
    for event in trace_events:
        payload = event.get("payload", {})
        total += payload.get("cost_usd", 0.0)
    return round(total, 8)


def _extract_token_counts(trace_events: list) -> dict[str, int]:
    """Sum input/output tokens from all llm_response and evaluation events."""
    input_tokens = 0
    output_tokens = 0
    for event in trace_events:
        payload = event.get("payload", {})
        input_tokens += payload.get("input_tokens", 0)
        output_tokens += payload.get("output_tokens", 0)
    return {"input": input_tokens, "output": output_tokens}


def _extract_guards(trace_events: list) -> list[str]:
    """Return names of all guards that fired during the run."""
    guards = []
    for event in trace_events:
        if event.get("event_type") == "guard_triggered":
            guard = event.get("payload", {}).get("guard")
            if guard:
                guards.append(guard)
    return guards


def _extract_source_count(state: dict) -> int:
    return len(state.get("research", {}).get("sources", []))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_experiment(exporter: str, session_id: str) -> dict:
    config = MultiAgentConfig(exporter=exporter)
    agent = OrchestratorAgent(config=config)

    print(f"\n{'=' * 62}")
    print(f"  Exporter          : {exporter}")
    print(f"  Session           : {session_id}")
    print(f"  Orchestrator model: {config.orchestrator_model}")
    print(f"  Researcher model  : {config.researcher_model}")
    print(f"  Evaluator model   : {config.evaluator_model}")
    print(f"  Sampling          : {config.sampling_rate}")
    print(f"  Queries           : {len(QUERIES)}")
    print(f"{'=' * 62}\n")

    query_results = []

    for q in QUERIES:
        print(f"  [{q['id']}] {q['type']}")
        print(f"        → {q['prompt'][:100]}{'...' if len(q['prompt']) > 100 else ''}")

        t0 = time.perf_counter()
        error = None
        state = None
        try:
            state = agent.run(q["prompt"], session_id=session_id)
        except Exception as exc:
            error = str(exc)
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)

        if state is not None:
            evaluation = state.get("evaluation", {})
            trace_events = state.get("trace_events", [])
            tokens = _extract_token_counts(trace_events)
            cost = _extract_cost_from_events(trace_events)
            guards = _extract_guards(trace_events)

            faithfulness = evaluation.get("faithfulness", 0.0)
            label = evaluation.get("label", "unknown")
            retry_count = state.get("retry_count", 0)
            hitl = state.get("hitl_required", False)
            source_count = _extract_source_count(state)
            final_answer_chars = len(state.get("final_answer", ""))
        else:
            evaluation = {}
            tokens = {"input": 0, "output": 0}
            cost = 0.0
            guards = []
            faithfulness = 0.0
            label = "error"
            retry_count = 0
            hitl = False
            source_count = 0
            final_answer_chars = 0

        status = "✓" if not error else "✗"
        hitl_flag = " ⚠ HITL" if hitl else ""
        guards_str = f" guards={guards}" if guards else ""
        print(
            f"        {status}  {latency_ms:.0f} ms  "
            f"faith={faithfulness:.2f}  retries={retry_count}  src={source_count}"
            f"{hitl_flag}{guards_str}"
        )
        print()

        query_results.append({
            "id": q["id"],
            "type": q["type"],
            "prompt": q["prompt"],
            "latency_ms": latency_ms,
            "faithfulness": round(faithfulness, 4),
            "label": label,
            "retry_count": retry_count,
            "hitl_required": hitl,
            "source_count": source_count,
            "final_answer_chars": final_answer_chars,
            "input_tokens": tokens["input"],
            "output_tokens": tokens["output"],
            "cost_usd": cost,
            "guards_fired": guards,
            "error": error,
        })

    totals = {
        "latency_ms": round(sum(r["latency_ms"] for r in query_results), 1),
        "input_tokens": sum(r["input_tokens"] for r in query_results),
        "output_tokens": sum(r["output_tokens"] for r in query_results),
        "cost_usd": round(sum(r["cost_usd"] for r in query_results), 8),
        "avg_faithfulness": round(
            sum(r["faithfulness"] for r in query_results) / len(query_results), 4
        ),
        "total_retries": sum(r["retry_count"] for r in query_results),
        "hitl_escalations": sum(1 for r in query_results if r["hitl_required"]),
        "errors": sum(1 for r in query_results if r["error"]),
        "guards_fired": [g for r in query_results for g in r["guards_fired"]],
    }

    return {
        "session_id": session_id,
        "exporter": exporter,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "orchestrator_model": config.orchestrator_model,
        "researcher_model": config.researcher_model,
        "evaluator_model": config.evaluator_model,
        "sampling_rate": config.sampling_rate,
        "low_confidence_threshold": config.low_confidence_threshold,
        "faithfulness_threshold": config.faithfulness_threshold,
        "queries": query_results,
        "totals": totals,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_summary(data: dict) -> None:
    print(f"\n{'=' * 72}")
    print("  SUMMARY")
    print(f"{'=' * 72}")
    print(
        f"  {'ID':<4}  {'Latency':>10}  {'Faith':>6}  "
        f"{'Retry':>5}  {'HITL':>5}  {'Cost':>10}  Status"
    )
    print(f"  {'-'*4}  {'-'*10}  {'-'*6}  {'-'*5}  {'-'*5}  {'-'*10}  ------")
    for r in data["queries"]:
        status = "OK" if not r["error"] else "ERROR"
        hitl = "yes" if r["hitl_required"] else "no"
        print(
            f"  {r['id']:<4}  {r['latency_ms']:>9.0f}ms"
            f"  {r['faithfulness']:>6.2f}"
            f"  {r['retry_count']:>5}"
            f"  {hitl:>5}"
            f"  ${r['cost_usd']:>9.6f}"
            f"  {status}"
        )
    t = data["totals"]
    print(f"  {'─'*4}  {'─'*10}  {'─'*6}  {'─'*5}  {'─'*5}  {'─'*10}")
    print(
        f"  {'TOT':<4}  {t['latency_ms']:>9.0f}ms"
        f"  {t['avg_faithfulness']:>6.2f}"
        f"  {t['total_retries']:>5}"
        f"  {t['hitl_escalations']:>5}"
        f"  ${t['cost_usd']:>9.6f}"
    )
    if t["errors"]:
        print(f"\n  ⚠  {t['errors']} query/queries failed — check 'error' fields in JSON.")
    if t["guards_fired"]:
        from collections import Counter
        counts = Counter(t["guards_fired"])
        print(f"  ⚠  Guards fired: {dict(counts)}")
    print()


def save_results(data: dict) -> Path:
    out_dir = ROOT / "experiments" / "multi_agent" / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{data['session_id']}.json"
    out_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return out_file


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a Multi-Agent experiment session and save results to JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--exporter",
        choices=["phoenix", "langfuse", "opik", "otel-stdout", "none"],
        required=True,
        help="Observability exporter to use for this session.",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        metavar="ID",
        help=(
            "Session ID used to group traces in the tool UI. "
            "Auto-generated as 'multi-<exporter>-YYYYMMDD-HHMMSS' if omitted."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    session_id = args.session_id or (
        f"multi-{args.exporter}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )

    data = run_experiment(exporter=args.exporter, session_id=session_id)
    print_summary(data)
    out_file = save_results(data)
    print(f"  Saved → {out_file.relative_to(ROOT)}\n")
