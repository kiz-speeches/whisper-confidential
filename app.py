"""GPU transcription prototype. Does not provide confidential computing."""
import io
import json
import os
import threading
import time
import urllib.request
from contextlib import asynccontextmanager
from pathlib import Path

import ctranslate2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from faster_whisper import WhisperModel
from huggingface_hub import snapshot_download

MODEL_REVISION = "536b0662742c02347bc0e980a01041f333bce120"
ROOT = Path(__file__).parent
MAX_AUDIO_BYTES = 64 * 1024 * 1024
lock = threading.Lock()
model = None


def transcribe(data: bytes, language: str | None = None):
    with lock:
        started = time.monotonic()
        segments, info = model.transcribe(
            io.BytesIO(data), language=language, beam_size=1,
            vad_filter=True, condition_on_previous_text=False,
        )
        items = [{"start": s.start, "end": s.end, "text": s.text} for s in segments]
    return {
        "text": "".join(s["text"] for s in items).strip(),
        "language": info.language, "segments": items,
        "duration": info.duration, "processing_seconds": round(time.monotonic() - started, 3),
    }


@asynccontextmanager
async def lifespan(app):
    global model
    if ctranslate2.get_cuda_device_count() != 1:
        raise RuntimeError("Expected exactly one allocated CUDA GPU")
    print("WHISPER-MODEL-LOAD device=cuda compute_type=float16", flush=True)
    model_path = os.environ.get("WHISPER_MODEL_PATH") or snapshot_download(
        repo_id="Systran/faster-whisper-small", revision=MODEL_REVISION,
        allow_patterns=["model.bin", "config.json", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"],
    )
    if os.environ.get('WHISPER_MODEL_PATH'):
        from verify_model import verify_model
        verify_model(Path(model_path), ROOT/'release/inputs.json')
    model = WhisperModel(model_path, device="cuda", compute_type="float16", num_workers=1)
    # Only a public upstream fixture is used and its transcript is not logged.
    smoke_audio = os.environ.get("WHISPER_SMOKE_AUDIO")
    if smoke_audio:
        result = transcribe(Path(smoke_audio).read_bytes(), "en")
    else:
        with urllib.request.urlopen(
            "https://raw.githubusercontent.com/openai/whisper/main/tests/jfk.flac", timeout=30,
        ) as response:
            result = transcribe(response.read(), "en")
    if "country" not in result["text"].lower():
        raise RuntimeError("CUDA transcription smoke test failed")
    print(json.dumps({"event": "WHISPER-CUDA-SMOKE-OK", "seconds": result["processing_seconds"]}), flush=True)
    yield
    model = None


app = FastAPI(title="Whisper GPU prototype", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/health")
def health():
    return {"ready": model is not None, "device": "cuda", "model": "small", "revision": MODEL_REVISION}


@app.get("/v1/runtime")
def runtime():
    return {
        "mode": "gpu-prototype", "device": "cuda", "model": "small",
        "model_revision": MODEL_REVISION, "confidential_computing": False,
        "attestation_available": False, "attestation_verified": False,
        "notice": "GPU-Prototyp ohne TEE-Schutz. Kein verifizierter Attestation-Report verfügbar.",
    }


@app.post("/v1/audio/transcriptions")
def transcription(file: UploadFile = File(...), language: str = Form("auto")):
    try:
        if language not in {"auto", "de", "en"}:
            raise HTTPException(status_code=400, detail="Unsupported language")
        audio = file.file.read(MAX_AUDIO_BYTES + 1)
        if not audio or len(audio) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio must be nonempty and at most 64 MiB")
        try:
            return transcribe(audio, None if language == "auto" else language)
        except Exception:
            raise HTTPException(status_code=400, detail="Audio could not be transcribed") from None
    finally:
        file.file.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, access_log=False)
