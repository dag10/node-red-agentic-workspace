#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/check-env.sh"

export HA_URL="$HOMEASSISTANT_URL"
export HA_TOKEN="$HOMEASSISTANT_TOKEN"
exec uvx hass-mcp
