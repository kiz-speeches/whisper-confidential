"""Build-time preparation only; the resulting image can start without model downloads."""
import hashlib
import json
import urllib.request
import shutil
from pathlib import Path

from huggingface_hub import snapshot_download

root = Path("/opt/whisper-model")
root.mkdir(parents=True, exist_ok=True)
revision = "536b0662742c02347bc0e980a01041f333bce120"
inputs = json.loads(Path('/app/release/inputs.json').read_text())
snapshot_download(
    repo_id="Systran/faster-whisper-small", revision=revision, local_dir=root,
    allow_patterns=["model.bin", "config.json", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"],
)
for entry in inputs['model']['files']:
    actual = hashlib.sha256((root/entry['path']).read_bytes()).hexdigest()
    if actual != entry['sha256']:
        raise RuntimeError('Model file hash mismatch: '+entry['path'])
audio = Path('/app/tests/fixtures/jfk.flac').read_bytes()
if hashlib.sha256(audio).hexdigest() != inputs['test_audio_sha256']:
    raise RuntimeError('Test audio hash mismatch')
(root/'jfk.flac').write_bytes(audio)
shutil.rmtree(root/'.cache', ignore_errors=True)
manifest = {
    "model_repository": "Systran/faster-whisper-small", "model_revision": revision,
    "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.iterdir()) if p.is_file()},
}
(root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
