#!/usr/bin/env python3
"""Build fixed Linux AMD64 OCI images; optionally repeat without layer cache."""
import argparse,hashlib,json,os,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--version',required=True)
parser.add_argument('--repeat',action='store_true')
parser.add_argument('--cpu-only',action='store_true')
parser.add_argument('--builder',default='whisper-release-builder')
args=parser.parse_args()
subprocess.run(['python3','tools/release.py','prepare','--version',args.version],cwd=ROOT,check=True)
info=json.loads((ROOT/'static/build-info.json').read_text())
builder_image=info['build_inputs']['buildkit_image']
if subprocess.run(['docker','buildx','inspect',args.builder],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
    subprocess.run(['docker','buildx','create','--name',args.builder,'--driver','docker-container','--driver-opt','image='+builder_image,'--bootstrap'],check=True)
else:
    image=subprocess.check_output(['docker','inspect','buildx_buildkit_'+args.builder+'0','--format','{{.Config.Image}}'],text=True).strip()
    if image!=builder_image:parser.error('Existing builder does not match the pinned BuildKit image')
components=[('cpu','attestation/Dockerfile')]+([] if args.cpu_only else [('gpu','Dockerfile')])
for name,_ in components:
    lock=ROOT/('attestation/requirements.lock' if name=='cpu' else 'release/gpu-requirements.lock')
    wheels=ROOT/'release/wheels'/name;wheels.mkdir(parents=True,exist_ok=True)
    expected={match[3] for line in lock.read_text().splitlines()
              if (match:=re.match(r'^([^=]+)==([^ ]+) --hash=sha256:([a-f0-9]{64})$',line))}
    def available():
        return {hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in wheels.glob('*.whl')}
    if not expected.issubset(available()):
        subprocess.run(['docker','run','--rm','--platform','linux/amd64','--user',f'{os.getuid()}:{os.getgid()}',
            '-v',str(ROOT)+':/work','-w','/work',info['build_inputs']['python_base'],'python','-m','pip','download',
            '--no-cache-dir','--only-binary=:all:','--no-deps','--require-hashes','-r',str(lock.relative_to(ROOT)),
            '-d',str(wheels.relative_to(ROOT))],check=True)
    if not expected.issubset(available()):parser.error(f'Incomplete or invalid {name} wheel inputs')
for pass_number in range(1,3 if args.repeat else 2):
    out=ROOT/'release/dist'/f'build-{pass_number}';out.mkdir(parents=True,exist_ok=True)
    for name,dockerfile in components:
        image=out/f'{name}.oci.tar'
        subprocess.run(['docker','buildx','build','--builder',args.builder,'--platform','linux/amd64','--no-cache',
          '--provenance=false','--sbom=false','--build-arg','SOURCE_DATE_EPOCH='+str(info['source_date_epoch']),
          '--build-context','wheels='+str(ROOT/'release/wheels'/name),
          '--output','type=oci,oci-mediatypes=true,rewrite-timestamp=true,dest='+str(image),
          '--metadata-file',str(out/f'{name}-build.json'),'-f',str(ROOT/dockerfile),str(ROOT)],check=True)
        first=subprocess.check_output(['python3',str(ROOT/'tools/release.py'),'image-digest',str(ROOT/'release/dist/build-1'/f'{name}.oci.tar')],text=True).strip()
        current=subprocess.check_output(['python3',str(ROOT/'tools/release.py'),'image-digest',str(image)],text=True).strip()
        if first!=current:parser.error(f'{name} is not reproducible: {first} != {current}')
        print(f'{name} pass {pass_number}: {current}',flush=True)
if not args.cpu_only:
    subprocess.run(['python3','tools/release.py','finalize','--cpu','release/dist/build-1/cpu.oci.tar',
                    '--gpu','release/dist/build-1/gpu.oci.tar','--output','release/dist/release-manifest.json'],cwd=ROOT,check=True)
print('Build finished. Reproducibility and hardware attestation are separate properties.',flush=True)
