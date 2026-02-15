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

# --- Check for uncommitted local changes ---
if [[ -f "$FLOWS_FILE" ]] && \
   [[ -n "$(git -C "$MYNODERED_DIR" status --porcelain -- nodered.json)" ]]; then
  echo "mynodered/nodered.json has uncommitted local changes." >&2
  echo "Please commit or discard them before downloading fresh flows." >&2
  exit 1
fi

# --- Download latest flows ---
echo "Downloading latest Node-RED flows..."
echo ""
"$PROJECT_DIR/helper-scripts/download-nodered-flows.sh" "$FLOWS_FILE"
echo ""

# --- Check what changed ---
is_new=false
if ! git -C "$MYNODERED_DIR" ls-files --error-unmatch nodered.json &>/dev/null; then
  is_new=true
fi

if [[ "$is_new" == false ]] && git -C "$MYNODERED_DIR" diff --quiet -- nodered.json; then
  echo "No changes since last download."
  exit 0
fi

if [[ "$is_new" == true ]]; then
  echo "Initial flow download complete."
else
  echo "Flows have changed since last download."
fi

echo ""
read -rp "Would you like to analyze the changes? [Y/n] " analyze
analyze="${analyze:-Y}"
if [[ "$analyze" =~ ^[Yy]$ ]]; then
  echo ""
  echo "TODO!"
  echo ""
fi

# --- Commit to submodule ---
git -C "$MYNODERED_DIR" add nodered.json
git -C "$MYNODERED_DIR" commit -m "Latest changes downloaded from Home Assistant."
echo ""
echo "Committed updated flows to mynodered/."
