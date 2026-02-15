#!/usr/bin/env bash
set -euo pipefail

# Verifies that the flows currently in Node-RED match the given file.
# Intended to be run before uploading modified flows, to catch concurrent
# changes made in Node-RED while the local copy was being edited.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -ne 1 ]]; then
  echo "Usage: check-nodered-flows-unchanged.sh <flows.json>" >&2
  echo "Exits 0 if Node-RED's current flows match the file, 1 if they differ." >&2
  exit 2
fi

LOCAL_FILE="$1"

if [[ ! -f "$LOCAL_FILE" ]]; then
  echo "Error: file not found: $LOCAL_FILE" >&2
  exit 2
fi

TMPDIR_WORK="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_WORK"' EXIT

LIVE_FILE="$TMPDIR_WORK/live.json"
LOCAL_NORMALIZED="$TMPDIR_WORK/local.json"

# Download current flows (already normalized by download script)
"$SCRIPT_DIR/download-nodered-flows.sh" "$LIVE_FILE" >&2

# Normalize the local file so key/entry order doesn't cause false diffs
"$SCRIPT_DIR/normalize-json.sh" "$LOCAL_FILE" "$LOCAL_NORMALIZED"

if diff -q "$LOCAL_NORMALIZED" "$LIVE_FILE" > /dev/null 2>&1; then
  echo "Flows match." >&2
  exit 0
else
  echo "Flows have diverged. Diff (local vs live):" >&2
  diff --unified=3 "$LOCAL_NORMALIZED" "$LIVE_FILE" >&2 || true
  exit 1
fi
