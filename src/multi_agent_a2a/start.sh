#!/usr/bin/env bash
# start.sh — Manage all A2A multi-agent services.
#
# Usage (run from anywhere):
#   ./src/multi_agent_a2a/start.sh          # kill any running instances, then start fresh
#   ./src/multi_agent_a2a/start.sh --stop   # kill running instances only
#
# Logs are written to logs/a2a/ in the project root.
# The active exporter is read from EXPORTER_A2A in .env.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RESEARCHER_PORT=8011
EVALUATOR_PORT=8012
ORCHESTRATOR_PORT=8002
UI_PORT=7862

LOG_DIR="$PROJECT_ROOT/logs/a2a"

# ── Helpers ───────────────────────────────────────────────────────────────────

_pids_on_port() {
    lsof -ti:"$1" 2>/dev/null || true
}

kill_port() {
    local port=$1 name=$2
    local pids
    pids=$(_pids_on_port "$port")
    if [[ -n "$pids" ]]; then
        printf "  Stopping %-22s port %-5s PIDs: %s\n" "$name" "$port" "$pids"
        echo "$pids" | xargs kill -TERM 2>/dev/null || true
        # Wait up to 4 s for graceful shutdown, then force-kill
        local i=0
        while [[ -n "$(_pids_on_port "$port")" && $i -lt 8 ]]; do
            sleep 0.5
            i=$((i + 1))
        done
        pids=$(_pids_on_port "$port")
        [[ -n "$pids" ]] && echo "$pids" | xargs kill -KILL 2>/dev/null || true
    else
        printf "  %-22s port %-5s not running\n" "$name" "$port"
    fi
}

wait_for_port() {
    local port=$1 name=$2 timeout=${3:-20}
    local i=0
    printf "  Waiting for %-22s port %s …" "$name" "$port"
    while [[ -z "$(_pids_on_port "$port")" ]]; do
        sleep 0.5
        i=$((i + 1))
        if [[ $i -ge $((timeout * 2)) ]]; then
            echo " TIMEOUT"
            echo "  Check log: $LOG_DIR/$name.log"
            return 1
        fi
    done
    echo " ready"
}

# ── Stop ──────────────────────────────────────────────────────────────────────

stop_all() {
    echo "Stopping A2A services…"
    kill_port "$UI_PORT"           "ui"
    kill_port "$ORCHESTRATOR_PORT" "orchestrator"
    kill_port "$EVALUATOR_PORT"    "evaluator"
    kill_port "$RESEARCHER_PORT"   "researcher"
    echo "Done."
}

# ── Start ─────────────────────────────────────────────────────────────────────

start_all() {
    cd "$PROJECT_ROOT"
    mkdir -p "$LOG_DIR"

    # Load .env so EXPORTER_A2A and API keys reach child processes
    if [[ -f .env ]]; then
        set -a
        # shellcheck disable=SC1091
        source .env
        set +a
    fi

    local exporter="${EXPORTER_A2A:-none}"
    echo "Starting A2A services  [exporter: $exporter]  (logs → $LOG_DIR/)"

    python -m src.multi_agent_a2a.researcher_service \
        > "$LOG_DIR/researcher.log" 2>&1 &
    wait_for_port "$RESEARCHER_PORT" "researcher"

    python -m src.multi_agent_a2a.evaluator_service \
        > "$LOG_DIR/evaluator.log" 2>&1 &
    wait_for_port "$EVALUATOR_PORT" "evaluator"

    uvicorn src.multi_agent_a2a.backend_a2a:app \
        --port "$ORCHESTRATOR_PORT" \
        > "$LOG_DIR/orchestrator.log" 2>&1 &
    wait_for_port "$ORCHESTRATOR_PORT" "orchestrator"

    python -m src.multi_agent_a2a.ui \
        > "$LOG_DIR/ui.log" 2>&1 &
    wait_for_port "$UI_PORT" "ui"

    echo ""
    echo "Services:"
    echo "  Researcher    http://127.0.0.1:$RESEARCHER_PORT"
    echo "  Evaluator     http://127.0.0.1:$EVALUATOR_PORT"
    echo "  Orchestrator  http://127.0.0.1:$ORCHESTRATOR_PORT"
    echo "  UI            http://127.0.0.1:$UI_PORT"
}

# ── Entry point ───────────────────────────────────────────────────────────────

case "${1:-}" in
    --stop)
        stop_all
        ;;
    "")
        stop_all
        echo ""
        start_all
        ;;
    *)
        echo "Usage: $0 [--stop]" >&2
        exit 1
        ;;
esac
