"""Small SNP CPU gateway. Whisper inference deliberately remains outside the TEE."""
import asyncio
import base64
import hashlib
import json
import os
import secrets
import time
from pathlib import Path

import httpx
import uvicorn
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from evidence import pack, b64

ROOT = Path(__file__).parent
GPU = os.environ.get('GPU_URL', 'http://whisper-gpu-prototype:8080')
AA = 'http://127.0.0.1:8006/aa/evidence'
DOMAIN = b'whisper-cpu-tee-v1'
MAX_AUDIO = 64 * 1024 * 1024
SESSION_TTL = 1800
sessions = {}
collateral = {}
lock = asyncio.Lock()
quote_lock = asyncio.Lock()
gpu_slots = asyncio.Semaphore(2)
client = httpx.AsyncClient(timeout=150)
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def decode(value, length=None):
    try:
        data = base64.b64decode(value, validate=True)
        if length is not None and len(data) != length:
            raise ValueError()
        return data
    except (ValueError, TypeError):
        raise HTTPException(400, 'Invalid cryptographic input')


async def bundle(report):
    r = report['attestation_report']
    raw = pack(report)
    t = r['reported_tcb']
    hwid = bytes(r['chip_id'][:8]).hex()
    cache_key = (hwid, tuple(sorted(t.items())))
    entry = collateral.get(cache_key)
    if not entry or entry['until'] < time.monotonic():
        if os.environ.get('AMD_KDS_ENABLED') != 'true':
            raise RuntimeError('AMD certificate fetch not enabled')
        # The user explicitly approved the AMD KDS HWID/TCB request before deployment.
        base = 'https://kdsintf.amd.com/vcek/v1/Turin/'
        params = {'fmcSPL': t['fmc'], 'blSPL': t['bootloader'], 'teeSPL': t['tee'],
                  'snpSPL': t['snp'], 'ucodeSPL': t['microcode']}
        vcek, chain, crl = await asyncio.gather(client.get(base+hwid, params=params),
                                               client.get(base+'cert_chain'), client.get(base+'crl'))
        for response in (vcek, chain, crl):
            response.raise_for_status()
        from cryptography import x509
        ask = x509.load_pem_x509_certificates(chain.content)[0].public_bytes(serialization.Encoding.DER)
        entry = {'until': time.monotonic()+3600, 'vcek': b64(vcek.content), 'ask': b64(ask), 'crl': b64(crl.content)}
        collateral[cache_key] = entry
    return {'report': b64(raw), **{k: entry[k] for k in ('vcek', 'ask', 'crl')}}


@app.middleware('http')
async def headers(request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response


def software_release():
    """Release metadata is informative until an enforced policy binds it to this workload."""
    path = ROOT/'build-info.json'
    if not path.is_file():
        return None
    return {'manifest': json.loads(path.read_text()), 'verified': False,
            'binding': 'not_attested_to_workload'}


@app.get('/health')
async def health():
    try:
        response = await client.get(GPU + '/health', timeout=5)
        response.raise_for_status()
        data = response.json()
        data['cpu_tee_gateway'] = True
        return data
    except Exception:
        return JSONResponse({'ready': False}, status_code=503)


@app.get('/v1/runtime')
async def runtime():
    return {'mode': 'cpu-tee-gpu-prototype', 'device': 'cuda', 'cpu_tee': 'AMD SEV-SNP',
            'confidential_computing': False, 'gpu_confidential_computing': False,
            'attestation_available': True, 'attestation_verified': False,
            'workload_policy_verified': False,
            'notice': 'CPU-Guest und Sitzungsschlüssel prüfbar. GPU-Verarbeitung und Anwendungspolicy sind nicht attestiert.'}


@app.post('/v1/attestation')
async def attest(request: Request):
    if int(request.headers.get('content-length', '0')) > 4096:
        raise HTTPException(413, 'Request too large')
    try:
        body = await request.json()
        nonce = decode(body['nonce'], 32)
        client_pub = decode(body['client_public_key'], 65)
        peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), client_pub)
    except (KeyError, ValueError, TypeError):
        raise HTTPException(400, 'Invalid attestation request')
    async with quote_lock:
        key = ec.generate_private_key(ec.SECP256R1())
        public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        sid = secrets.token_bytes(16)
        binding = hashlib.sha256(DOMAIN+b'\0'+nonce+public+client_pub+sid).hexdigest()
        try:
            response = await client.get(AA, params={'runtime_data': binding}, timeout=15)
            response.raise_for_status()
            evidence = await bundle(response.json())
        except Exception:
            # Never substitute a mock quote or mark evidence as server-verified.
            raise HTTPException(503, 'CPU attestation or AMD certificates unavailable')
        shared = key.exchange(ec.ECDH(), peer)
        def aes(direction):
            return AESGCM(HKDF(algorithm=hashes.SHA256(), length=32, salt=nonce,
                              info=DOMAIN+b'/'+direction).derive(shared))
        async with lock:
            now = time.monotonic()
            for old in list(sessions):
                if sessions[old]['expires'] < now:
                    del sessions[old]
            if len(sessions) >= 128:
                raise HTTPException(429, 'Too many active sessions')
            sessions[sid.hex()] = {'request': aes(b'request'), 'response': aes(b'response'),
                                   'expires': now+SESSION_TTL, 'sequence': -1}
        return {'evidence': evidence, 'server_public_key': b64(public), 'session_id': sid.hex(),
                'expires_in': SESSION_TTL, 'report_data': binding,
                # Envelope metadata only: never insert a placeholder into signed AMD evidence.
                'gpu_attestation': {'status': 'not_available', 'placeholder': True,
                                    'evidence': None, 'verified': False,
                                    'confidential_computing': False},
                'software_release': software_release()}


@app.post('/v1/audio/transcriptions')
async def transcribe(request: Request):
    sid = request.headers.get('x-session', '')
    language = request.headers.get('x-language', '')
    if language not in ('de', 'en', 'auto'):
        raise HTTPException(400, 'Invalid language')
    try:
        sequence = int(request.headers['x-sequence'])
        if sequence < 0 or sequence > 2**32:
            raise ValueError()
        iv = decode(request.headers['x-iv'], 12)
    except (ValueError, KeyError):
        raise HTTPException(400, 'Invalid encrypted audio headers')
    async with lock:
        session = sessions.get(sid)
        if not session or session['expires'] <= time.monotonic():
            raise HTTPException(401, 'Session expired. Request CPU attestation again.')
        if sequence <= session['sequence']:
            raise HTTPException(409, 'Replayed audio request')
    data = bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data) > MAX_AUDIO+16:
            raise HTTPException(413, 'Audio too large')
    try:
        aad = f'whisper-cpu-tee-v1/request|{sid}|{sequence}|{language}'.encode()
        audio = session['request'].decrypt(iv, bytes(data), aad)
    except Exception:
        raise HTTPException(400, 'Audio authentication failed')
    async with lock:
        if sequence <= session['sequence']:
            raise HTTPException(409, 'Replayed audio request')
        session['sequence'] = sequence
    async with gpu_slots:
        try:
            # Explicit prototype boundary: plaintext leaves CPU TEE here.
            response = await client.post(GPU + '/v1/audio/transcriptions',
                                         files={'file': ('audio.wav', audio, 'application/octet-stream')},
                                         data={'language': language})
        except httpx.HTTPError:
            raise HTTPException(502, 'GPU inference unavailable')
    if not response.is_success:
        raise HTTPException(response.status_code, 'GPU transcription failed')
    iv = secrets.token_bytes(12)
    aad = f'whisper-cpu-tee-v1/response|{sid}|{sequence}'.encode()
    encrypted = session['response'].encrypt(iv, response.content, aad)
    return {'iv': b64(iv), 'ciphertext': b64(encrypted)}


if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', '8080')), access_log=False)
