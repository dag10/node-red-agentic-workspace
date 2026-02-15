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

# --- Set up mynodered/ directory (Node-RED flow tracking) ---
MYNODERED_DIR="$PROJECT_DIR/mynodered"

if [[ ! -d "$MYNODERED_DIR" ]]; then
  echo "The mynodered/ directory doesn't exist yet."
  echo "This is where your Node-RED flows will be tracked in a separate git repo."
  echo ""
  read -rp "Git repo URL for tracking Node-RED flows (leave empty to init a new local repo): " nodered_repo_url

  if [[ -n "$nodered_repo_url" ]]; then
    git -C "$PROJECT_DIR" submodule add "$nodered_repo_url" mynodered
    echo ""
    echo "Cloned $nodered_repo_url as submodule at mynodered/"
  else
    git init "$MYNODERED_DIR"
    git -C "$MYNODERED_DIR" commit --allow-empty -m "Initial commit"
    echo ""
    echo "Initialized empty git repo at mynodered/."
    echo "You can add a remote later by re-running init.sh."
  fi
  echo ""
elif [[ -d "$MYNODERED_DIR/.git" ]] || [[ -f "$MYNODERED_DIR/.git" ]]; then
  # Dir exists and is a git repo (or submodule with .git file)
  if ! git -C "$MYNODERED_DIR" remote get-url origin &>/dev/null; then
    echo "mynodered/ exists but has no remote configured."
    echo ""
    read -rp "Git repo URL to use as upstream remote (leave empty to skip): " nodered_repo_url

    if [[ -n "$nodered_repo_url" ]]; then
      git -C "$MYNODERED_DIR" remote add origin "$nodered_repo_url"

      # Verify remote is empty before pushing
      if git -C "$MYNODERED_DIR" ls-remote --heads origin 2>/dev/null | grep -q .; then
        echo "ERROR: Remote repo is not empty. Please provide an empty repository." >&2
        git -C "$MYNODERED_DIR" remote remove origin
        exit 1
      fi

      branch=$(git -C "$MYNODERED_DIR" branch --show-current)
      git -C "$MYNODERED_DIR" push -u origin "${branch:-main}"

      # Register as a proper submodule if not already
      if ! git -C "$PROJECT_DIR" config -f .gitmodules --get submodule.mynodered.path &>/dev/null; then
        git -C "$PROJECT_DIR" config -f .gitmodules submodule.mynodered.path mynodered
        git -C "$PROJECT_DIR" config -f .gitmodules submodule.mynodered.url "$nodered_repo_url"
        git -C "$PROJECT_DIR" submodule init mynodered 2>/dev/null || true
      fi

      echo ""
      echo "Remote added and pushed. mynodered/ registered as submodule."
    fi
    echo ""
  fi
else
  echo "ERROR: mynodered/ exists but is not a git repository." >&2
  echo "Please remove or rename it and re-run init.sh." >&2
  exit 1
fi

if [[ ${#missing[@]} -gt 0 ]]; then
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
fi

echo ""
echo "You're all good to go!"

if [[ ! -f "$MYNODERED_DIR/nodered.json" ]]; then
  echo ""
  read -rp "Would you like to download your Node-RED flows now? [Y/n] " download
  download="${download:-Y}"
  if [[ "$download" =~ ^[Yy]$ ]]; then
    echo ""
    "$PROJECT_DIR/download-flows.sh"
  fi
fi
