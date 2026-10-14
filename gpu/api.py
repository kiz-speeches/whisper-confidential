"""GPU transcription prototype. Does not provide confidential computing."""
import io
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import ctranslate2
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from faster_whisper import WhisperModel
from verify_model import verify_model

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
    model_path = os.environ.get('WHISPER_MODEL_PATH', '/opt/whisper-model')
    verify_model(Path(model_path), ROOT/'model-inputs.json')
    model = WhisperModel(model_path, device="cuda", compute_type="float16", num_workers=1)
    yield
    model = None


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


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
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get('PORT', '8080')), access_log=False)
