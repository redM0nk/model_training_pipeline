#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q "pip==21.3.1" "setuptools==59.6.0" "wheel==0.37.1"
pip install -q -r requirements.txt

export FLASK_APP=app.py
exec python app.py
