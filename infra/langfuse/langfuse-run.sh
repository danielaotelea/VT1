#!/usr/bin/env bash
set -euo pipefail

LANGFUSE_DIR="/Users/danielaotelea/Documents/ZHAW/Semester3/VT1/langfuse"

if [ ! -d "$LANGFUSE_DIR" ]; then
  echo "ERROR: Langfuse directory not found: $LANGFUSE_DIR"
  exit 1
fi

cd "$LANGFUSE_DIR"

if [ "${1:-}" = "--stop" ]; then
  echo "Stopping Langfuse ..."
  docker compose down
else
  echo "Starting Langfuse (UI at http://localhost:3000) ..."
  docker compose up
fi
