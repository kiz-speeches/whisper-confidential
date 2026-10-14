#!/usr/bin/env bash
set -euo pipefail
python -m venv /runtime/venv
/runtime/venv/bin/pip install --no-cache-dir --no-compile --only-binary=:all: --require-hashes -r /source/requirements.lock
mkdir -p /runtime/app/static/attestation
cp /source/gateway.py /source/evidence.py /runtime/app/
cp /source/index.html /source/style.css /source/client.js /source/attestation.js /source/pcm-worklet.js /runtime/app/static/
if [ -f /source/build-info.json ]; then cp /source/build-info.json /runtime/app/static/; fi
cp /source/wasm_exec.js /runtime/app/static/attestation/
cat /wasm/*/part > /runtime/app/static/attestation/verifier.wasm
cd /runtime/app/static/attestation
sha256sum -c /source/verifier.sha256
chown -R 1000:1000 /runtime
