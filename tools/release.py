#!/usr/bin/env python3
"""Deterministic source/release manifests. Hash comparison is not hardware attestation."""
import argparse, hashlib, json, re, subprocess, tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()
def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args]).decode().strip()
def inventory():
    paths = git('ls-files', '-z').split('\0')
    entries = []
    for name in sorted(p for p in paths if p):
        path = ROOT/name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'Unsupported tracked source: {name}')
        entries.append({'path': name, 'sha256': digest(path), 'executable': bool(path.stat().st_mode & 0o111)})
    if not entries:
        raise ValueError('No tracked source files')
    return entries
def packages(path):
    return {m[1]: m[2] for line in path.read_text().splitlines()
            if (m := re.match(r'^([A-Za-z0-9_.-]+)==([^\s]+)',line))}
def prepare(version):
    if git('status','--porcelain'):
        raise ValueError('Release builds require a clean committed checkout')
    inputs = json.loads((ROOT/'build/inputs.json').read_text())
    source = inventory()
    result = {'schema_version': 1, 'version': version, 'git_commit': git('rev-parse','HEAD'),
              'source_date_epoch': int(git('show','-s','--format=%ct','HEAD')),
              'source_tree_sha256': hashlib.sha256(canonical(source)).hexdigest(),
              'source_files': source, 'build_inputs': inputs,
              'versions': {'cpu_packages': packages(ROOT/'cpu/requirements.lock'),
                           'gpu_packages': packages(ROOT/'gpu/requirements.lock')},
              'attestation': {'workload_policy_enforced': False, 'expected_host_data': None,
                              'gpu_evidence': None, 'software_versions_verified': False}}
    (ROOT/'.build').mkdir(exist_ok=True)
    (ROOT/'.build/build-info.json').write_text(json.dumps(result,indent=2)+'\n')
    print(result['source_tree_sha256'])

def image_digest(path):
    with tarfile.open(path) as tar:
        def read(name):
            item = tar.getmember(name)
            if not item.isfile() or item.size > 8*1024*1024:
                raise ValueError('Unexpected OCI metadata')
            return tar.extractfile(item).read()
        def blob(descriptor):
            value = descriptor['digest']
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', value):
                raise ValueError('Unsupported OCI digest')
            name = 'blobs/sha256/'+value[7:]
            member = tar.getmember(name)
            if not member.isfile() or member.size != descriptor['size']:
                raise ValueError('OCI blob size mismatch')
            with tar.extractfile(member) as source:
                actual = hashlib.file_digest(source,'sha256').hexdigest()
            if actual != value[7:]:
                raise ValueError('OCI blob hash mismatch')
            return name
        index = json.loads(read('index.json'))
        choices = [d for d in index['manifests'] if d.get('platform',{}).get('architecture','amd64') == 'amd64'
                   and d.get('platform',{}).get('os','linux') == 'linux']
        if len(choices) != 1:
            raise ValueError('Expected exactly one Linux AMD64 image')
        descriptor = choices[0]
        manifest = json.loads(read(blob(descriptor)))
        blob(manifest['config'])
        for layer in manifest['layers']:
            blob(layer)
        return descriptor['digest']

def finalize(cpu, gpu, output):
    info = json.loads((ROOT/'.build/build-info.json').read_text())
    if git('status','--porcelain') or info['git_commit'] != git('rev-parse','HEAD'):
        raise ValueError('Source changed since prepare')
    if info['source_tree_sha256'] != hashlib.sha256(canonical(inventory())).hexdigest():
        raise ValueError('Source content changed since prepare')
    info['images'] = {'cpu_gateway': {'platform_digest':image_digest(cpu), 'archive_sha256':digest(cpu)},
                      'gpu_worker': {'platform_digest':image_digest(gpu), 'archive_sha256':digest(gpu)}}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(info,indent=2)+'\n')
    (output.parent/'SHA256SUMS').write_text(f'{digest(output)}  {output.name}\n'+
        f'{digest(cpu)}  {cpu.name}\n{digest(gpu)}  {gpu.name}\n')
    print('Release manifest written; workload/GPU attestation remain explicitly unverified')

def verify(manifest_path, cpu, gpu):
    manifest = json.loads(manifest_path.read_text())
    if manifest['source_tree_sha256'] != hashlib.sha256(canonical(inventory())).hexdigest():
        raise ValueError('Local source differs from release')
    for name,path in (('cpu_gateway',cpu),('gpu_worker',gpu)):
        if image_digest(path) != manifest['images'][name]['platform_digest']:
            raise ValueError(f'Local {name} image differs from release')
    print('MATCH: source tree and both platform image digests. This is build verification, not TEE verification.')

parser=argparse.ArgumentParser(description=__doc__)
sub=parser.add_subparsers(dest='command',required=True)
p=sub.add_parser('prepare');p.add_argument('--version',required=True)
p=sub.add_parser('finalize')
for flag in ('cpu','gpu','output'):p.add_argument('--'+flag,type=Path,required=True)
p=sub.add_parser('verify')
for flag in ('manifest','cpu','gpu'):p.add_argument('--'+flag,type=Path,required=True)
p=sub.add_parser('image-digest');p.add_argument('archive',type=Path)
if __name__=='__main__':
    args=parser.parse_args()
    try:
        if args.command=='prepare':prepare(args.version)
        elif args.command=='finalize':finalize(args.cpu,args.gpu,args.output)
        elif args.command=='verify':verify(args.manifest,args.cpu,args.gpu)
        else:print(image_digest(args.archive))
    except (ValueError,KeyError,tarfile.TarError) as error:
        parser.exit(1,str(error)+'\n')
