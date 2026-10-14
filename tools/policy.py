#!/usr/bin/env python3
"""Create reviewable SNP Init-Data from the exact released CPU image."""
import argparse, hashlib, json, os, subprocess, tarfile, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def harden(policy, image):
    marker = '    allow_create_container_input\n'
    if policy.count(marker) != 1 or policy.count('CopyFileRequest if {') != 1:
        raise ValueError('Unexpected genpolicy rules; review the pinned generator')
    policy = policy.replace(marker, marker+'    whisper_image_sources_allowed\n', 1)
    policy = policy.replace('CopyFileRequest if {', 'CopyFileRequest if {\n'
                            '    input.file_type == "Regular"\n'
                            '    input.file_size <= 16384\n'
                            '    input.symlink_target == null', 1)
    policy += '''
whisper_image_sources_allowed if {
    sources := [s.source | s := input.storages[_]; s.driver == "image_guest_pull"]
    count(sources) == 1
    sources[0] == "pause"
    input.OCI.Annotations["io.kubernetes.cri.container-type"] == "sandbox"
}

whisper_image_sources_allowed if {
    sources := [s.source | s := input.storages[_]; s.driver == "image_guest_pull"]
    count(sources) == 1
    sources[0] == IMAGE
    input.OCI.Annotations["io.kubernetes.cri.container-type"] == "container"
    input.OCI.Annotations["io.kubernetes.cri.image-name"] == IMAGE
}
'''.replace('IMAGE', json.dumps(image))
    for name in ('ExecProcessRequest', 'SetPolicyRequest', 'AllowRequestsFailingPolicy'):
        if f'default {name} := false' not in policy:
            raise ValueError('Required deny default missing: '+name)
    return policy

def initdata(policy):
    # Kata 3.32 hashes the exact uncompressed TOML bytes, not parsed/canonical data.
    raw = ('version = "0.1.0"\nalgorithm = "sha256"\n\n[data]\n'
           '"policy.rego" = '+json.dumps(policy)+'\n').encode()
    return raw, hashlib.sha256(raw).hexdigest()

def install_tools(inputs, target):
    spec = inputs['policy_tools']; archive = target/'kata-tools.tar.zst'
    target.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        with urllib.request.urlopen(spec['url'], timeout=90) as response:
            archive.write_bytes(response.read())
    if hashlib.sha256(archive.read_bytes()).hexdigest() != spec['sha256']:
        raise ValueError('Kata policy-tools archive hash mismatch')
    from compression.zstd import ZstdFile  # Build tooling uses Python 3.14; APIs use 3.12.
    with ZstdFile(archive, 'rb') as stream, tarfile.open(fileobj=stream, mode='r|') as tar:
        tar.extractall(target, filter='data')
    return target/'opt/kata'

def generate(manifest_path, output, tools=None):
    manifest = json.loads(manifest_path.read_text())
    inputs = manifest['build_inputs']; contract = json.loads((ROOT/'policy/contract.json').read_text())
    image = manifest['images']['cpu_gateway']['registry_reference']
    if not image.endswith('@'+manifest['images']['cpu_gateway']['platform_digest']):
        raise ValueError('CPU registry reference must use the released digest')
    tools = tools or install_tools(inputs, ROOT/'.build/policy-tools')
    defaults = tools/'share/defaults/kata-containers'
    settings = json.loads((defaults/'genpolicy-settings.json').read_text())
    settings['kata_config']['oci_version'] = contract['oci_version']
    settings['cluster_config']['guest_pull'] = True
    for section in ('pause_container', 'other_container'):
        settings[section]['Annotations']['io.katacontainers.pkg.oci.bundle_path'] = (
            '/run/k3s/containerd/io.containerd.runtime.v2.task/k8s.io/$(bundle-id)')
    settings['request_defaults']['CreateContainerRequest']['allow_env_regex'] = []
    settings['request_defaults']['CopyFileRequest'] = ['$(sfprefix)(resolv\\.conf|hosts|hostname|termination-log)$']
    settings['request_defaults']['ExecProcessRequest'] = {'allowed_commands': [], 'regex': []}
    # This is the generator's security input, not the operational cluster deployment.
    pod = {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {
        'name': contract['pod_name'], 'namespace': contract['namespace'],
        'annotations': {'io.katacontainers.config.hypervisor.kernel_params':
                        'agent.guest_components_rest_api=all agent.log=info'}}, 'spec': {'containers': [{
        'name': contract['container_name'], 'image': image, 'command': contract['command'],
        'env': [{'name': k, 'value': v} for k,v in sorted(contract['environment'].items())],
        'securityContext': contract['security_context']}]}}
    output.mkdir(parents=True, exist_ok=True)
    projection = output/'policy-input.json'; projection.write_text(json.dumps(pod,sort_keys=True)+'\n')
    settings_path = output/'policy-settings.json';settings_path.write_text(json.dumps(settings,sort_keys=True)+'\n')
    env = {**os.environ, 'RUST_LOG': 'warn'}
    raw = subprocess.check_output([str(tools/'bin/genpolicy'), '-y', str(projection), '-r',
          '-j', str(settings_path), '-p', str(defaults/'rules.rego')], env=env, text=True)
    policy = harden(raw, image); (output/'policy.rego').write_text(policy)
    data, host_data = initdata(policy); (output/'initdata.toml').write_bytes(data)
    reference = {'schema_version': 1, 'version': manifest['version'], 'git_commit': manifest['git_commit'],
        'measurement': inputs['cpu_guest_reference']['measurement'], 'expected_host_data': host_data,
        'cpu_image': image, 'policy_sha256': hashlib.sha256(policy.encode()).hexdigest(),
        'verification_scope': 'cpu_guest_session_key_and_cpu_workload',
        'gpu_verified': False}
    (output/'attestation-policy.json').write_text(json.dumps(reference,indent=2)+'\n')
    manifest['attestation'].update({'expected_host_data': host_data, 'policy_sha256': reference['policy_sha256'],
        'binding_status': 'generated; client must verify signed HOST_DATA',
        'workload_policy_enforced': False, 'software_versions_verified': False})
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')
    print('Policy and expected SNP HOST_DATA:', host_data)
    return reference

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();generate(args.manifest,args.output)
