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

# --- Check that the server hasn't changed since we last downloaded ---
LAST_DOWNLOADED="$MYNODERED_DIR/nodered-last-downloaded.json"
server_diverged=false
if [[ -f "$LAST_DOWNLOADED" ]]; then
  echo "Checking that the server hasn't changed since last download..."
  echo ""
  if ! "$PROJECT_DIR/helper-scripts/check-nodered-flows-unchanged.sh" "$LAST_DOWNLOADED" 2>/dev/null; then
    server_diverged=true
    echo ""
    echo "WARNING: The server's flows have changed since you last downloaded." >&2
    echo "Uploading will OVERWRITE those server changes with your local version." >&2
    echo ""
  fi
fi

# --- Check for changes to upload ---
if [[ "$server_diverged" == false ]]; then
  echo "Checking for differences between local flows and server..."
  echo ""
  if "$PROJECT_DIR/helper-scripts/check-nodered-flows-unchanged.sh" "$FLOWS_FILE" 2>/dev/null; then
    echo "Local flows match the server. Nothing to upload."
    exit 0
  fi
fi

echo "Local flows differ from the server."
echo ""

# --- Confirm upload ---
if [[ "$server_diverged" == true ]]; then
  read -rp "Upload anyway, OVERWRITING server changes? [y/N] " confirm
else
  read -rp "Upload and deploy these flows to Node-RED? [y/N] " confirm
fi
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
  echo "Upload cancelled."
  exit 0
fi

# --- Upload ---
echo ""
echo "Uploading flows to Node-RED..."
echo ""
"$PROJECT_DIR/helper-scripts/upload-nodered-flows.sh" "$FLOWS_FILE"

# Now that our local flows are what's deployed, update the last-downloaded snapshot.
cp "$FLOWS_FILE" "$LAST_DOWNLOADED"

# Commit the updated snapshot to the submodule.
git -C "$MYNODERED_DIR" add nodered-last-downloaded.json
git -C "$MYNODERED_DIR" commit -m "Deployed flows."

echo ""
echo "Deploy complete."
