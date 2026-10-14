#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/verifier"
export GOCACHE=${GOCACHE:-/tmp/whisper-attestation-gocache}
export GOMODCACHE=${GOMODCACHE:-/tmp/whisper-attestation-modcache}
export GOTOOLCHAIN=go1.26.8
mkdir -p ../build
GOOS=js GOARCH=wasm go build -buildvcs=false -trimpath -o ../build/verifier.wasm .
cp "$(go env GOROOT)/lib/wasm/wasm_exec.js" ../build/wasm_exec.js
