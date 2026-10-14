#!/usr/bin/env bash
set -euo pipefail
if [[ ! -f /runtime/installed ]] || ! cmp -s /app/requirements.txt /runtime/requirements.txt; then
  python -m venv /runtime/venv
  /runtime/venv/bin/pip install --no-cache-dir -r /app/requirements.txt
  mkdir -p /runtime/hf
  chown -R 1000:1000 /runtime
  cp /app/requirements.txt /runtime/requirements.txt
  touch /runtime/installed
fi
