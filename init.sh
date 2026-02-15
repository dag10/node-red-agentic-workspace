#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$PROJECT_DIR/.env"

# --- Ensure uv is installed (needed for uvx) ---
if ! command -v uv &>/dev/null; then
  echo "'uv' is not installed (needed for the 'uvx' command)."
  read -rp "Would you like to install it now? [Y/n] " answer
  answer="${answer:-Y}"
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # The installer adds uv to ~/.local/bin; make sure it's on PATH for this session
    export PATH="$HOME/.local/bin:$PATH"
    if ! command -v uv &>/dev/null; then
      echo "ERROR: uv was installed but still not found on PATH." >&2
      echo "Try opening a new terminal or adding ~/.local/bin to your PATH." >&2
      exit 1
    fi
    echo "uv $(uv --version) installed successfully."
  else
    echo "uv is required to continue. Please install it: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
  fi
fi

REQUIRED_VARS=(
  HOMEASSISTANT_URL
  HOMEASSISTANT_TOKEN
)

DEFAULTS=(
  "http://homeassistant.local:8123"
  ""
)

PROMPTS=(
  "Home Assistant URL"
  "Home Assistant long-lived access token"
)

# Load existing .env if present
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

missing=()
missing_prompts=()
for i in "${!REQUIRED_VARS[@]}"; do
  var="${REQUIRED_VARS[$i]}"
  if [[ -z "${!var:-}" ]]; then
    missing+=("$var")
    missing_prompts+=("${PROMPTS[$i]}")
  fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "Some environment variables are missing. Let's set them up."
  echo ""

  new_lines=()
  for i in "${!missing[@]}"; do
    var="${missing[$i]}"
    prompt="${missing_prompts[$i]}"
    default="${DEFAULTS[$i]:-}"
    if [[ -n "$default" ]]; then
      prompt="$prompt [${default}]"
    fi
    while true; do
      read -rp "$prompt: " value
      value="${value:-$default}"
      if [[ -n "$value" ]]; then
        break
      fi
      echo "  $var cannot be empty, please enter a value."
    done
    export "$var=$value"
    new_lines+=("$var=$value")
  done

  # Append new vars to .env (create if needed)
  for line in "${new_lines[@]}"; do
    echo "$line" >> "$ENV_FILE"
  done
  chmod 600 "$ENV_FILE"

  echo ""
  echo ".env updated."
fi

echo ""
echo "Verifying Home Assistant MCP connection..."
echo ""

# NOTE: --model flag uses the short alias; claude cli resolves it to the full model id.
output=$(claude --model haiku --print \
  "Verify the home-assistant MCP server is loaded and call the get_version tool. Reply with ONLY the version string if it works, or 'FAIL: <reason>' if not." \
  2>&1)

if [[ "$output" == FAIL* ]]; then
  echo "Verification failed: $output" >&2
  exit 1
fi

echo "Home Assistant MCP connected — HA version $output"
echo ""
echo "You're all good to go!"
