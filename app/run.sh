#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

PYTHON_BIN="${PYTHON:-python3}"

# Recreate the venv if it's missing or inherits system site-packages.
# A venv that sees the host's tensorflow/etc. makes pip's resolver bail out.
needs_recreate=0
if [[ ! -d .venv ]]; then
  needs_recreate=1
elif [[ ! -f .venv/pyvenv.cfg ]] || ! grep -q '^include-system-site-packages = false' .venv/pyvenv.cfg; then
  needs_recreate=1
fi
if [[ "$needs_recreate" -eq 1 ]]; then
  rm -rf .venv
  "$PYTHON_BIN" -m venv .venv
fi

VPY="$HERE/.venv/bin/python"
PIP_OPTS=(--disable-pip-version-check --no-warn-script-location --no-cache-dir)

# Pin the toolchain to the last versions that support Python 3.6.
"$VPY" -m pip install "${PIP_OPTS[@]}" "pip==21.3.1"
"$VPY" -m pip install "${PIP_OPTS[@]}" --use-deprecated=legacy-resolver \
    "setuptools==59.6.0" "wheel==0.37.1"
"$VPY" -m pip install "${PIP_OPTS[@]}" --use-deprecated=legacy-resolver \
    -r requirements.txt

export FLASK_APP=app.py
exec "$VPY" app.py
