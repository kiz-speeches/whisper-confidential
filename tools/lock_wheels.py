"""Freeze the downloaded Python 3.12/Linux AMD64 wheels, including transitive dependencies."""
import argparse, hashlib
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('wheel_directory', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
packages = {}
for wheel in sorted(args.wheel_directory.glob('*.whl')):
    name, version = wheel.name.split('-')[:2]
    name = name.lower().replace('_', '-')
    assert name not in packages, f'Multiple wheels for {name}'
    packages[name] = (version, hashlib.file_digest(wheel.open('rb'), 'sha256').hexdigest())
assert packages, 'No wheels'
args.output.write_text('# Python 3.12, Linux AMD64; complete dependency set; binary wheels only.\n'+
                       ''.join(f'{name}=={version} --hash=sha256:{digest}\n' for name,(version,digest) in sorted(packages.items())))
print(f'Locked {len(packages)} packages into {args.output}')
