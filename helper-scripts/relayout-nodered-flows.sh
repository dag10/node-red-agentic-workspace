#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: relayout-nodered-flows.sh <flows.json> [--baseline <file>] [--dry-run] [--verbose]" >&2
  echo "" >&2
  echo "Auto-relayout Node-RED groups containing modified nodes." >&2
  echo "Compares the file on disk against a baseline to detect structural changes." >&2
  echo "" >&2
  echo "Options:" >&2
  echo "  --baseline <file>  Compare against this file instead of the last git commit." >&2
  echo "  --dry-run          Show what would change without modifying the file." >&2
  echo "  --verbose          Print detailed progress to stderr." >&2
  exit 1
}

# Parse arguments: extract --baseline and the flows file, pass the rest through.
BASELINE=""
FLOWS_FILE=""
PASSTHROUGH_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --baseline)
      if [[ $# -lt 2 ]]; then
        echo "Error: --baseline requires a file argument" >&2
        exit 1
      fi
      BASELINE="$2"
      shift 2
      ;;
    --dry-run|--verbose)
      PASSTHROUGH_ARGS+=("$1")
      shift
      ;;
    -*)
      echo "Error: unknown option: $1" >&2
      usage
      ;;
    *)
      if [[ -z "$FLOWS_FILE" ]]; then
        FLOWS_FILE="$1"
      else
        echo "Error: unexpected argument: $1" >&2
        usage
      fi
      shift
      ;;
  esac
done

if [[ -z "$FLOWS_FILE" ]]; then
  usage
fi

if [[ ! -f "$FLOWS_FILE" ]]; then
  echo "Error: file not found: $FLOWS_FILE" >&2
  exit 1
fi

BEFORE_FILE="$(mktemp)"
trap 'rm -f "$BEFORE_FILE"' EXIT

if [[ -n "$BASELINE" ]]; then
  # Resolve to absolute path before copying.
  BASELINE="$(cd "$(dirname "$BASELINE")" && pwd)/$(basename "$BASELINE")"
  if [[ ! -f "$BASELINE" ]]; then
    echo "Error: baseline file not found: $BASELINE" >&2
    exit 1
  fi
  cp "$BASELINE" "$BEFORE_FILE"
else
  # Default: compare against the last git commit.
  file_dir="$(cd "$(dirname "$FLOWS_FILE")" && pwd)"
  file_name="$(basename "$FLOWS_FILE")"
  # NOTE: If the file has never been committed, git show fails and we
  # fall back to an empty JSON array -- making everything show as "added."
  git -C "$file_dir" show "HEAD:$file_name" > "$BEFORE_FILE" 2>/dev/null || echo "[]" > "$BEFORE_FILE"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

exec python3 "$SCRIPT_DIR/relayout-nodered-flows.py" "$FLOWS_FILE" "$BEFORE_FILE" "${PASSTHROUGH_ARGS[@]}"
