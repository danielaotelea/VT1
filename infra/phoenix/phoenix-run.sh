#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="arize-phoenix"

if [ "${1:-}" = "--stop" ]; then
  echo "Stopping Phoenix ..."
  docker stop "$CONTAINER_NAME" && docker rm "$CONTAINER_NAME"
else
  echo "Starting Phoenix (UI at http://localhost:6006) ..."
  docker run --name "$CONTAINER_NAME" -p 6006:6006 -p 4317:4317 -i -t arizephoenix/phoenix:latest
fi
