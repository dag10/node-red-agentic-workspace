#!/usr/bin/env bash
set -euo pipefail

# Other scripts can use this script like so:
# ```bash
# source "$(dirname "${BASH_SOURCE[0]}")/check-env.sh"
# ```

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

REQUIRED_VARS=(
  HOMEASSISTANT_URL
  HOMEASSISTANT_TOKEN
)

missing=()

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Error: .env file not found at $ENV_FILE" >&2
  for var in "${REQUIRED_VARS[@]}"; do
    missing+=("$var")
  done
else
  # shellcheck source=/dev/null
  source "$ENV_FILE"

  for var in "${REQUIRED_VARS[@]}"; do
    if [[ -z "${!var:-}" ]]; then
      missing+=("$var")
    fi
  done
fi

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "Missing required environment variables:" >&2
  for var in "${missing[@]}"; do
    echo "  $var" >&2
  done
  exit 1
fi
