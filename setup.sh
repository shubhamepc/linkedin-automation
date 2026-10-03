#!/usr/bin/env bash
# One-time setup (macOS / Linux). Python 3.10+ chahiye — uv ho to woh khud le aata hai.
set -euo pipefail
cd "$(dirname "$0")"

if command -v uv >/dev/null 2>&1; then
  uv venv --python 3.12 .venv
  uv pip install --python .venv/bin/python -r requirements.txt
else
  PY=$(command -v python3.13 || command -v python3.12 || command -v python3.11 || command -v python3.10 || true)
  if [ -z "$PY" ]; then
    echo "Python 3.10+ nahi mila. Sabse aasan: curl -LsSf https://astral.sh/uv/install.sh | sh   phir dobara ./setup.sh"
    exit 1
  fi
  "$PY" -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

# Chrome na ho to backup browser
if [ ! -d "/Applications/Google Chrome.app" ] && ! command -v google-chrome >/dev/null 2>&1; then
  .venv/bin/python -m playwright install chromium
fi

[ -f .env ] || cp .env.example .env

echo
echo "✅ Setup done. Ab guided setup shuru ho raha hai..."
echo
.venv/bin/python run.py start
