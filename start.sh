#!/usr/bin/env bash
set -euo pipefail
export PYTHONUNBUFFERED=1
export HF_HOME=/runtime/hf
export HF_HUB_DISABLE_TELEMETRY=1
export DO_NOT_TRACK=1
export LD_LIBRARY_PATH="$(/runtime/venv/bin/python -c 'import site; from pathlib import Path; p=Path(site.getsitepackages()[0]); print(str(p/"nvidia/cublas/lib")+":"+str(p/"nvidia/cudnn/lib"))'):${LD_LIBRARY_PATH:-}"
exec /runtime/venv/bin/python /app/app.py
