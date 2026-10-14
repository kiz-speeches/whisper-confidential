"""Build-time preparation only; the resulting image can start without model downloads."""
import hashlib
import json
import shutil
from pathlib import Path

from huggingface_hub import snapshot_download

root = Path("/opt/whisper-model")
root.mkdir(parents=True, exist_ok=True)
inputs = json.loads(Path('/build/inputs.json').read_text())
revision = inputs['model']['revision']
snapshot_download(
    repo_id=inputs['model']['repository'], revision=revision, local_dir=root,
    allow_patterns=[entry['path'] for entry in inputs['model']['files']],
)
for entry in inputs['model']['files']:
    actual = hashlib.sha256((root/entry['path']).read_bytes()).hexdigest()
    if actual != entry['sha256']:
        raise RuntimeError('Model file hash mismatch: '+entry['path'])
shutil.rmtree(root/'.cache', ignore_errors=True)
Path('/opt/model-inputs.json').write_text(json.dumps({'model': inputs['model']}, sort_keys=True)+'\n')
