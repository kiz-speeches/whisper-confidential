"""Protocol tests with explicitly mocked hardware evidence and GPU responses.
These tests never assert that mock hardware evidence is valid attestation.
"""
import base64
import hashlib
import json
import secrets
import unittest
import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'cpu'))
import api as gateway


class Backend:
    def __init__(self):
        self.audio = []
        self.binding = None

    async def get(self, url, **kw):
        self.binding = kw['params']['runtime_data']
        return httpx.Response(200, json={'mock': True}, request=httpx.Request('GET', url))

    async def post(self, url, **kw):
        self.audio.append(kw['files']['file'][1])
        return httpx.Response(200, json={'text': 'GPU fixture transcript', 'processing_seconds': 1},
                              request=httpx.Request('POST', url))


class Protocol(unittest.TestCase):
    def setUp(self):
        gateway.sessions.clear()
        self.backend = Backend()
        self.client_patch = patch.object(gateway, 'client', self.backend)
        self.client_patch.start()
        self.bundle_patch = patch.object(gateway, 'bundle', AsyncMock(return_value={'mock': True}))
        self.bundle_patch.start()
        self.browser = TestClient(gateway.app)
        self.nonce = secrets.token_bytes(32)
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.public = self.key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        response = self.browser.post('/v1/attestation', json={'nonce': gateway.b64(self.nonce), 'client_public_key': gateway.b64(self.public)})
        self.assertEqual(response.status_code, 200)
        self.quote = response.json()
        public = base64.b64decode(self.quote['server_public_key'])
        peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)
        shared = self.key.exchange(ec.ECDH(), peer)
        self.request_key = AESGCM(HKDF(algorithm=hashes.SHA256(), length=32, salt=self.nonce, info=gateway.DOMAIN+b'/request').derive(shared))
        self.response_key = AESGCM(HKDF(algorithm=hashes.SHA256(), length=32, salt=self.nonce, info=gateway.DOMAIN+b'/response').derive(shared))

    def tearDown(self):
        self.client_patch.stop()
        self.bundle_patch.stop()

    def packet(self, sequence=0, language='de', audio=b'RIFF synthetic fixture'):
        sid = self.quote['session_id']
        iv = secrets.token_bytes(12)
        encrypted = self.request_key.encrypt(iv, audio, f'whisper-cpu-tee-v1/request|{sid}|{sequence}|{language}'.encode())
        headers = {'X-Session': sid, 'X-IV': gateway.b64(iv), 'X-Sequence': str(sequence), 'X-Language': language}
        return headers, encrypted

    def test_key_bound_and_bidirectional_encryption(self):
        expected = hashlib.sha256(gateway.DOMAIN+b'\0'+self.nonce+base64.b64decode(self.quote['server_public_key'])+
                                  self.public+bytes.fromhex(self.quote['session_id'])).hexdigest()
        self.assertEqual(self.backend.binding, expected)
        headers, encrypted = self.packet()
        self.assertNotIn(b'RIFF', encrypted)
        response = self.browser.post('/v1/audio/transcriptions', headers=headers, content=encrypted)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.backend.audio, [b'RIFF synthetic fixture'])
        body = response.json()
        clear = self.response_key.decrypt(base64.b64decode(body['iv']), base64.b64decode(body['ciphertext']),
                                          f"whisper-cpu-tee-v1/response|{self.quote['session_id']}|0".encode())
        self.assertEqual(json.loads(clear)['text'], 'GPU fixture transcript')
        self.assertNotIn('GPU fixture transcript', response.text)
        self.assertEqual(self.browser.post('/v1/audio/transcriptions', headers=headers, content=encrypted).status_code, 409)
        self.assertEqual(len(self.backend.audio), 1)

    def test_tampering_is_rejected_before_gpu(self):
        headers, encrypted = self.packet()
        bad = encrypted[:-1]+bytes([encrypted[-1]^1])
        self.assertEqual(self.browser.post('/v1/audio/transcriptions', headers=headers, content=bad).status_code, 400)
        headers['X-Language'] = 'en'
        self.assertEqual(self.browser.post('/v1/audio/transcriptions', headers=headers, content=encrypted).status_code, 400)
        self.assertEqual(self.backend.audio, [])

    def test_missing_and_expired_sessions(self):
        headers, encrypted = self.packet()
        gateway.sessions[self.quote['session_id']]['expires'] = 0
        self.assertEqual(self.browser.post('/v1/audio/transcriptions', headers=headers, content=encrypted).status_code, 401)
        headers['X-Session'] = 'unknown'
        self.assertEqual(self.browser.post('/v1/audio/transcriptions', headers=headers, content=encrypted).status_code, 401)
        self.assertEqual(self.backend.audio, [])

    def test_cpu_failure_never_falls_back_to_placeholder(self):
        existing = set(gateway.sessions)
        with patch.object(gateway, 'bundle', AsyncMock(side_effect=RuntimeError('CPU evidence unavailable'))):
            response = self.browser.post('/v1/attestation', json={
                'nonce': gateway.b64(self.nonce), 'client_public_key': gateway.b64(self.public)})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('evidence', response.json())
        self.assertEqual(set(gateway.sessions), existing)
        self.assertEqual(self.backend.audio, [])

    def test_api_does_not_serve_frontend_or_interactive_docs(self):
        for path in ('/', '/static/index.html', '/docs', '/redoc', '/openapi.json'):
            self.assertEqual(self.browser.get(path).status_code, 404, path)


if __name__ == '__main__':
    unittest.main()
