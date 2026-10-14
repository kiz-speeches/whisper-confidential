#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ -z ${KUBECONFIG:-} ]]; then
  echo 'Set KUBECONFIG to the cluster kubeconfig first.' >&2
  exit 1
fi
kubectl create configmap whisper-prototype-source -n confidential-inference \
  --from-file="$root/app.py" --from-file="$root/requirements.txt" \
  --from-file="$root/bootstrap.sh" --from-file="$root/start.sh" \
  --from-file="$root/static/index.html" --from-file="$root/static/client.js" \
  --from-file="$root/static/style.css" --from-file="$root/static/pcm-worklet.js" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "$root/k8s/deployment.yaml"
bash "$root/attestation/build.sh"
python "$root/attestation/deploy.py"
kubectl -n confidential-inference rollout status deployment/whisper-cpu-gateway --timeout=180s
kubectl apply -f "$root/k8s/ingress.yaml"
