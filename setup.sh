#!/usr/bin/env bash
# One-time setup (macOS / Linux). Needs Python 3.10+ — installs uv to get it if missing.
set -euo pipefail
cd "$(dirname "$0")"

PY_OK=$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3.10 || true)
if ! command -v uv >/dev/null 2>&1 && [ -z "$PY_OK" ]; then
  echo "Python 3.10+ not found — installing uv (official installer from astral.sh)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

if command -v uv >/dev/null 2>&1; then
  uv venv --allow-existing --python 3.12 .venv
  uv pip install --python .venv/bin/python -r requirements.txt
else
  PY=$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3.10 || true)
  if [ -z "$PY" ]; then
    echo "Python 3.10+ not found. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh   then run: bash setup.sh"
    exit 1
  fi
  "$PY" -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

# backup browser in case Google Chrome is not installed
if [ ! -d "/Applications/Google Chrome.app" ] && ! command -v google-chrome >/dev/null 2>&1; then
  .venv/bin/python -m playwright install chromium
fi

[ -f .env ] || cp .env.example .env

echo
echo "✅ Install done. Starting the guided setup..."
echo
.venv/bin/python run.py start
