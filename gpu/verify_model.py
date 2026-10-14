"""Check model files against the hashes embedded in the application image."""
import hashlib,json
from pathlib import Path
def verify_model(root: Path, inputs: Path):
    expected=json.loads(inputs.read_text())['model']['files']
    permitted={entry['path'] for entry in expected}
    if any(p.name not in permitted for p in root.iterdir()):
        raise RuntimeError('Unexpected model directory content')
    for entry in expected:
        path=root/entry['path']
        if not path.is_file() or path.is_symlink():
            raise RuntimeError('Missing or redirected model file: '+entry['path'])
        with path.open('rb') as source:actual=hashlib.file_digest(source,'sha256').hexdigest()
        if actual!=entry['sha256']:raise RuntimeError('Model file hash mismatch: '+entry['path'])
