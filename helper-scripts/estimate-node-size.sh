#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: estimate-node-size.sh <flows.json> <command> [args...]" >&2
  echo "Run with --help for full command list." >&2
  exit 1
fi

FLOWS_FILE="$1"

if [[ ! -f "$FLOWS_FILE" ]]; then
  echo "Error: file not found: $FLOWS_FILE" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/estimate-node-size.py" "$@"
