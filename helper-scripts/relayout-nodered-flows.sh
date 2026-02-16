#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: relayout-nodered-flows.sh <flows.json> [--dry-run] [--verbose]" >&2
  echo "" >&2
  echo "Auto-relayout Node-RED groups containing modified nodes." >&2
  echo "Compares the file on disk against its most recently committed" >&2
  echo "version. If there is no committed version, treats everything as new." >&2
  exit 1
}

if [[ $# -lt 1 ]]; then
  usage
fi

FLOWS_FILE="$1"
shift

if [[ ! -f "$FLOWS_FILE" ]]; then
  echo "Error: file not found: $FLOWS_FILE" >&2
  exit 1
fi

file_dir="$(cd "$(dirname "$FLOWS_FILE")" && pwd)"
file_name="$(basename "$FLOWS_FILE")"

BEFORE_FILE="$(mktemp)"
trap 'rm -f "$BEFORE_FILE"' EXIT

# NOTE: If the file has never been committed, git show fails and we
# fall back to an empty JSON array — making everything show as "added."
git -C "$file_dir" show "HEAD:$file_name" > "$BEFORE_FILE" 2>/dev/null || echo "[]" > "$BEFORE_FILE"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec python3 "$SCRIPT_DIR/relayout-nodered-flows.py" "$FLOWS_FILE" "$BEFORE_FILE" "$@"
