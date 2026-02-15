#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/check-env.sh"

INPUT_FILE="${1:-mynodered/nodered.json}"

# NOTE: The HA REST API's /api/hassio/* endpoints return 401 for long-lived tokens,
# but the websocket API's supervisor/api type works. We use the websocket to get
# the ingress URL and create a session, then upload flows over HTTP with that session.
exec uv run --with websockets "$SCRIPT_DIR/upload-nodered-flows.py" \
  "$HOMEASSISTANT_URL" \
  "$HOMEASSISTANT_TOKEN" \
  "$INPUT_FILE"
