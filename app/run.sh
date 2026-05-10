#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

PYTHON_BIN="${PYTHON:-python3}"

# Recreate the venv if it's missing, broken, or inherits system site-packages.
# A venv that sees the host's tensorflow/etc. makes pip's resolver bail out.
needs_recreate=0
if [[ ! -d .venv ]]; then
  needs_recreate=1
elif [[ ! -x .venv/bin/python ]]; then
  needs_recreate=1
elif [[ ! -f .venv/pyvenv.cfg ]] || ! grep -q '^include-system-site-packages = false' .venv/pyvenv.cfg; then
  needs_recreate=1
fi
if [[ "$needs_recreate" -eq 1 ]]; then
  rm -rf .venv
  # Create without pip; we bootstrap it ourselves below to handle hosts where
  # ensurepip is missing or broken.
  "$PYTHON_BIN" -m venv --without-pip .venv
fi

VPY="$HERE/.venv/bin/python"

# Bootstrap pip into the venv: try ensurepip first, fall back to get-pip.py.
if ! "$VPY" -c 'import pip' 2>/dev/null; then
  if ! "$VPY" -m ensurepip --upgrade --default-pip 2>/dev/null; then
    GETPIP="$(mktemp /tmp/get-pip.XXXXXX.py)"
    trap 'rm -f "$GETPIP"' EXIT
    GETPIP_URL="https://bootstrap.pypa.io/pip/3.6/get-pip.py"
    if command -v curl >/dev/null 2>&1; then
      curl -fsSL "$GETPIP_URL" -o "$GETPIP"
    elif command -v wget >/dev/null 2>&1; then
      wget -q "$GETPIP_URL" -O "$GETPIP"
    else
      echo "ERROR: pip missing in venv and neither curl nor wget is available." >&2
      exit 1
    fi
    "$VPY" "$GETPIP"
    rm -f "$GETPIP"
    trap - EXIT
  fi
fi

PIP_OPTS=(--disable-pip-version-check --no-warn-script-location --no-cache-dir)

# Pin pip first; legacy-resolver flag exists from pip 20.3+.
"$VPY" -m pip install "${PIP_OPTS[@]}" "pip==21.3.1"
"$VPY" -m pip install "${PIP_OPTS[@]}" --use-deprecated=legacy-resolver \
    "setuptools==59.6.0" "wheel==0.37.1"
"$VPY" -m pip install "${PIP_OPTS[@]}" --use-deprecated=legacy-resolver \
    -r requirements.txt

export FLASK_APP=app.py
exec "$VPY" app.py
