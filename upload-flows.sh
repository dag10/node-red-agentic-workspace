#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MYNODERED_DIR="$PROJECT_DIR/mynodered"
FLOWS_FILE="$MYNODERED_DIR/nodered.json"

# --- Verify environment and mynodered/ setup ---
source "$PROJECT_DIR/helper-scripts/check-env.sh"

if [[ ! -d "$MYNODERED_DIR/.git" ]] && [[ ! -f "$MYNODERED_DIR/.git" ]]; then
  echo "mynodered/ is not set up yet. Run init.sh first." >&2
  exit 1
fi

# --- Check that flows file exists ---
if [[ ! -f "$FLOWS_FILE" ]]; then
  echo "mynodered/nodered.json not found. Run download-flows.sh first." >&2
  exit 1
fi

# --- Check for changes to upload ---
echo "Checking for differences between local flows and server..."
echo ""
if "$PROJECT_DIR/helper-scripts/check-nodered-flows-unchanged.sh" "$FLOWS_FILE" 2>/dev/null; then
  echo "Local flows match the server. Nothing to upload."
  exit 0
fi

echo "Local flows differ from the server."
echo ""

# --- Confirm upload ---
read -rp "Upload and deploy these flows to Node-RED? [y/N] " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
  echo "Upload cancelled."
  exit 0
fi

# --- Upload ---
echo ""
echo "Uploading flows to Node-RED..."
echo ""
"$PROJECT_DIR/helper-scripts/upload-nodered-flows.sh" "$FLOWS_FILE"
echo ""
echo "Deploy complete."
