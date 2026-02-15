#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage:" >&2
  echo "  summarize-nodered-flows-diff.sh <before.json> <after.json>" >&2
  echo "  summarize-nodered-flows-diff.sh --git <flows.json>" >&2
  echo "" >&2
  echo "With --git, compares the file on disk against its most recently" >&2
  echo "committed version in the file's git repo. If there is no committed" >&2
  echo "version, diffs against an empty baseline." >&2
  exit 1
}

if [[ $# -eq 2 && "$1" == "--git" ]]; then
  AFTER_FILE="$2"
  if [[ ! -f "$AFTER_FILE" ]]; then
    echo "Error: file not found: $AFTER_FILE" >&2
    exit 1
  fi

  file_dir="$(cd "$(dirname "$AFTER_FILE")" && pwd)"
  file_name="$(basename "$AFTER_FILE")"

  BEFORE_FILE="$(mktemp)"
  trap 'rm -f "$BEFORE_FILE"' EXIT

  # NOTE: If the file has never been committed, git show fails and we
  # fall back to an empty JSON array — making everything show as "added."
  git -C "$file_dir" show "HEAD:$file_name" > "$BEFORE_FILE" 2>/dev/null || echo "[]" > "$BEFORE_FILE"

elif [[ $# -eq 2 ]]; then
  BEFORE_FILE="$1"
  AFTER_FILE="$2"
  for f in "$BEFORE_FILE" "$AFTER_FILE"; do
    if [[ ! -f "$f" ]]; then
      echo "Error: file not found: $f" >&2
      exit 1
    fi
  done
else
  usage
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/summarize-nodered-flows-diff.py" "$BEFORE_FILE" "$AFTER_FILE"
