#!/usr/bin/env bash
set -euo pipefail
if [[ -z ${KUBECONFIG:-} ]]; then
  echo 'Set KUBECONFIG to the cluster kubeconfig first.' >&2
  exit 1
fi
echo 'Öffne https://whisper.speeches.dev (CPU-Attestation und GPU-Inferenz).'
echo 'Kubernetes-Portforward funktioniert beim CoCo-Gast nicht; für lokale Diagnose wird ein SSH-Tunnel verwendet.'
cpu_service_ip=$(kubectl -n confidential-inference get service whisper-cpu-gateway -o jsonpath='{.spec.clusterIP}')
echo 'Lokale Diagnose: http://127.0.0.1:8780'
ssh_config=${WHISPER_SSH_CONFIG:-$HOME/.ssh/config}
exec ssh -F "$ssh_config" -o ExitOnForwardFailure=yes -N -L "127.0.0.1:8780:$cpu_service_ip:8080" "${WHISPER_SSH_HOST:-sec2}"
