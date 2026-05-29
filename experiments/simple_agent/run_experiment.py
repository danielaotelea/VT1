#!/usr/bin/env python3
"""Simple Agent — Experiment Runner (Round 1).

Runs a fixed query set against SimpleAgent with one observability exporter,
records latency / token counts / cost per query, and saves a JSON result file
to experiments/simple_agent/runs/.

Usage
-----
    # Run with Phoenix (must be running at PHOENIX_COLLECTOR_ENDPOINT)
    python experiments/simple_agent/run_experiment.py --exporter phoenix

    # Explicit session ID (used to group traces in the tool UI)
    python experiments/simple_agent/run_experiment.py --exporter langfuse --session-id round1-langfuse-001

    # Dry-run with no tracing (sanity check, no API key needed)
    python experiments/simple_agent/run_experiment.py --exporter none

Results are saved to:
    experiments/simple_agent/runs/<session-id>.json
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

from src.simple_agent.agent import build_agent, main as agent_main
from src.simple_agent.config import AgentConfig

# ---------------------------------------------------------------------------
# Fixed query set — identical across all tools to enable fair comparison.
# Queries are ordered by increasing trace complexity (number of tool calls).
# ---------------------------------------------------------------------------

QUERIES = [
    {
        "id": "Q1",
        "description": "Single tool call",
        "prompt": "What is 6 multiplied by 7?",
        "expected": "42",
    },
    {
        "id": "Q2",
        "description": "Two sequential tool calls — same type",
        "prompt": "Add 27 and 73, then multiply the result by 2.",
        "expected": "200",
    },
    {
        "id": "Q3",
        "description": "Two sequential tool calls — different types",
        "prompt": "Divide 100 by 4, then add 13.",
        "expected": "38.0",
    },
    {
        "id": "Q4",
        "description": "Chained output between calls",
        "prompt": "Multiply 8 by 9, then divide the result by 6.",
        "expected": "12.0",
    },
    {
        "id": "Q5",
        "description": "Three tool calls — longest trace",
        "prompt": "What is 15 divided by 3? Then multiply that by 5. Then add 10.",
        "expected": "35.0",
    },
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_experiment(exporter: str, session_id: str) -> dict:
    config = AgentConfig(exporter=exporter)
    agent = build_agent(config=config)

    print(f"\n{'=' * 62}")
    print(f"  Exporter  : {exporter}")
    print(f"  Session   : {session_id}")
    print(f"  Model     : {config.model_name}")
    print(f"  Sampling  : {config.sampling_rate}")
    print(f"  Queries   : {len(QUERIES)}")
    print(f"{'=' * 62}\n")

    query_results = []

    for q in QUERIES:
        print(f"  [{q['id']}] {q['description']}")
        print(f"        → {q['prompt']}")

        # Reset cost tracker so each query is measured independently
        agent.cost_tracker.records.clear()

        t0 = time.perf_counter()
        error = None
        try:
            output = agent_main(q["prompt"], agent=agent, session_id=session_id)
        except Exception as exc:
            output = f"ERROR: {exc}"
            error = str(exc)
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)

        tokens = agent.cost_tracker.total_tokens()
        cost = round(agent.cost_tracker.total_cost(), 8)

        status = "✓" if not error else "✗"
        print(f"        {status}  {latency_ms:.0f} ms  "
              f"in={tokens['input']} out={tokens['output']}  ${cost:.6f}")
        print()

        query_results.append({
            "id": q["id"],
            "description": q["description"],
            "prompt": q["prompt"],
            "expected": q["expected"],
            "output": output,
            "latency_ms": latency_ms,
            "input_tokens": tokens["input"],
            "output_tokens": tokens["output"],
            "cost_usd": cost,
            "error": error,
        })

    totals = {
        "latency_ms": round(sum(r["latency_ms"] for r in query_results), 1),
        "input_tokens": sum(r["input_tokens"] for r in query_results),
        "output_tokens": sum(r["output_tokens"] for r in query_results),
        "cost_usd": round(sum(r["cost_usd"] for r in query_results), 8),
        "errors": sum(1 for r in query_results if r["error"]),
    }

    return {
        "session_id": session_id,
        "exporter": exporter,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "model": config.model_name,
        "sampling_rate": config.sampling_rate,
        "queries": query_results,
        "totals": totals,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_summary(data: dict) -> None:
    print(f"\n{'=' * 62}")
    print("  SUMMARY")
    print(f"{'=' * 62}")
    print(f"  {'ID':<4}  {'Latency':>10}  {'In tok':>7}  {'Out tok':>7}  {'Cost (USD)':>12}  Status")
    print(f"  {'-'*4}  {'-'*10}  {'-'*7}  {'-'*7}  {'-'*12}  ------")
    for r in data["queries"]:
        status = "OK" if not r["error"] else "ERROR"
        print(
            f"  {r['id']:<4}  {r['latency_ms']:>9.0f}ms"
            f"  {r['input_tokens']:>7}"
            f"  {r['output_tokens']:>7}"
            f"  ${r['cost_usd']:>11.6f}"
            f"  {status}"
        )
    t = data["totals"]
    print(f"  {'─'*4}  {'─'*10}  {'─'*7}  {'─'*7}  {'─'*12}")
    print(
        f"  {'TOT':<4}  {t['latency_ms']:>9.0f}ms"
        f"  {t['input_tokens']:>7}"
        f"  {t['output_tokens']:>7}"
        f"  ${t['cost_usd']:>11.6f}"
    )
    if t["errors"]:
        print(f"\n  ⚠  {t['errors']} query/queries failed — check 'error' fields in JSON.")
    print()


def save_results(data: dict) -> Path:
    out_dir = ROOT / "experiments" / "simple_agent" / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{data['session_id']}.json"
    out_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return out_file


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a Simple Agent experiment session and save results to JSON.",
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
            "Auto-generated as 'simple-<exporter>-YYYYMMDD-HHMMSS' if omitted."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    session_id = args.session_id or (
        f"simple-{args.exporter}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    )

    data = run_experiment(exporter=args.exporter, session_id=session_id)
    print_summary(data)
    out_file = save_results(data)
    print(f"  Saved → {out_file.relative_to(ROOT)}\n")
