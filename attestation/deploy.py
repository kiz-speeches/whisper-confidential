#!/usr/bin/env python3
"""Prototype source deployment, until the image-building pipeline has push access.

The CPU service image can be built with Dockerfile; deployment currently uses
guest-pulled Python plus immutable ConfigMaps. No registry admin credentials.
"""
import base64
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
K = ['kubectl']  # Uses the caller's KUBECONFIG or standard kubectl context.
NAMESPACE = 'confidential-inference'


def apply(resource):
    subprocess.run(K+['apply', '--server-side', '--field-manager=whisper-cpu-prototype', '-f', '-'], input=json.dumps(resource).encode(), check=True)


if __name__ == '__main__':
    policy = json.loads((ROOT/'static/attestation-policy.json').read_text())
    if len(policy.get('measurement', '')) != 96:
        raise SystemExit('An administrator-recorded CPU guest measurement is required.')
    apply({'apiVersion': 'v1', 'kind': 'ConfigMap',
           'metadata': {'name': 'whisper-cpu-policy', 'namespace': NAMESPACE},
           'data': {'attestation-policy.json': (ROOT/'static/attestation-policy.json').read_text()}})
    data = {}
    for name in ('gateway.py', 'evidence.py', 'requirements.txt', 'requirements.lock', 'bootstrap.sh'):
        data[name] = (ROOT/'attestation'/name).read_text()
    for name in ('index.html', 'style.css', 'client.js', 'attestation.js', 'pcm-worklet.js'):
        data[name] = (ROOT/'static'/name).read_text()
    if (ROOT/'static/build-info.json').is_file():
        data['build-info.json'] = (ROOT/'static/build-info.json').read_text()
    data['wasm_exec.js'] = (ROOT/'attestation/build/wasm_exec.js').read_text()
    wasm = (ROOT/'attestation/build/verifier.wasm').read_bytes()
    digest = hashlib.sha256(wasm).hexdigest()
    data['verifier.sha256'] = digest+'  verifier.wasm\n'
    source_digest = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]
    source_name = 'whisper-cpu-source-'+source_digest
    apply({'apiVersion': 'v1', 'kind': 'ConfigMap', 'immutable': True,
           'metadata': {'name': source_name, 'namespace': NAMESPACE, 'labels': {'app': 'whisper-cpu-gateway'}}, 'data': data})
    parts = []
    for i, at in enumerate(range(0, len(wasm), 700000)):
        name = 'whisper-cpu-wasm-'+digest[:12]+'-'+str(i)
        apply({'apiVersion': 'v1', 'kind': 'ConfigMap', 'immutable': True,
               'metadata': {'name': name, 'namespace': NAMESPACE, 'labels': {'app': 'whisper-cpu-gateway'}},
               'binaryData': {'part': base64.b64encode(wasm[at:at+700000]).decode()}})
        parts.append({'name': 'wasm-'+str(i), 'configMap': {'name': name}})
    import yaml
    resources = list(yaml.safe_load_all((ROOT/'k8s/cpu-gateway.yaml').read_text()))
    pod = resources[0]['spec']['template']['spec']
    pod['volumes'] += [{'name': 'source', 'configMap': {'name': source_name}}, {'name': 'runtime', 'emptyDir': {'sizeLimit': '2Gi'}}] + parts
    pod['initContainers'][0]['volumeMounts'] += [{'name': p['name'], 'mountPath': '/wasm/'+f'{i:03}', 'readOnly': True} for i,p in enumerate(parts)]
    for resource in resources:
        apply(resource)
