#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/check-env.sh"

script_id="${1:?Usage: get-ha-script.sh <script_name>}"
# Accept either "script.foo" or just "foo"
script_id="${script_id#script.}"

response=$(curl -s -f \
  -H "Authorization: Bearer $HOMEASSISTANT_TOKEN" \
  "$HOMEASSISTANT_URL/api/config/script/config/$script_id") || {
  echo "Failed to fetch script '$script_id' from Home Assistant." >&2
  exit 1
}

echo "$response" | uv run --quiet --with pyyaml python3 -c "
import sys, json, yaml
data = json.load(sys.stdin)
yaml.safe_dump(data, sys.stdout, default_flow_style=False, sort_keys=False)
"
