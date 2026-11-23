#!/usr/bin/env bash
# Run Duplicate Image Finder from source on Linux / macOS (the run.bat of Windows).
# Creates .venv, installs the requirements once (again when they change), starts the app.
set -euo pipefail
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
VPY=.venv/bin/python

if [ ! -x "$VPY" ]; then
    echo "[setup] Creating virtual environment in .venv ..."
    "$PY" -m venv .venv
fi
STAMP=.venv/deps_installed.txt
if ! cat requirements.txt requirements-optional.txt | cmp -s - "$STAMP" 2>/dev/null; then
    echo "[setup] Installing dependencies ..."
    "$VPY" -m pip install --upgrade pip
    "$VPY" -m pip install -r requirements.txt
    grep -v '^#' requirements-optional.txt | grep -v '^\s*$' | while read -r pkg; do
        "$VPY" -m pip install "$pkg" || echo "[warn] optional $pkg failed to install - that format will be unavailable"
    done
    cat requirements.txt requirements-optional.txt > "$STAMP"
fi
[ -f models/dinov2_vits14_224.onnx ] || echo "[warn] models/dinov2_vits14_224.onnx is missing - crop detection will be disabled"
exec "$VPY" main.py "$@"
