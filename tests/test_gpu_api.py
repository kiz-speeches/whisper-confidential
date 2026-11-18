"""GPU boundary tests with mocked CUDA/decoder; model files are really hashed.

These test startup, decoder settings and honest identity reporting. They do not
claim GPU hardware, model accuracy or attestation verification.
"""
import hashlib
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

GPU = Path(__file__).resolve().parent.parent / 'gpu'
sys.path.insert(0, str(GPU))


class GpuBoundary(unittest.TestCase):
    def setUp(self):
        self.factory = Mock()
        self.cuda = SimpleNamespace(get_cuda_device_count=Mock(return_value=1))
        spec = importlib.util.spec_from_file_location('whisper_gpu_under_test', GPU/'api.py')
        self.api = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'ctranslate2': self.cuda, 'faster_whisper': SimpleNamespace(WhisperModel=self.factory)}):
            spec.loader.exec_module(self.api)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.model = self.root/'weights'
        self.model.mkdir()
        (self.model/'model.bin').write_bytes(b'test weights')
        identity = {'name': 'large-v3-turbo', 'repository': 'test/model', 'revision': 'a'*40,
                    'files': [{'path': 'model.bin', 'sha256': hashlib.sha256(b'test weights').hexdigest()}]}
        (self.root/'model-inputs.json').write_text(json.dumps({'model': identity}))
        self.api.ROOT = self.root
        self.environment = patch.dict(os.environ, {'WHISPER_MODEL_PATH': str(self.model)})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_startup_reports_only_the_identity_of_verified_loaded_weights(self):
        self.assertEqual(self.api.health()['model'], None)
        async def check():
            async with self.api.lifespan(self.api.app):
                self.assertEqual(self.api.health(), {'ready': True, 'device': 'cuda', 'model': 'large-v3-turbo', 'revision': 'a'*40})
                runtime = self.api.runtime()
                self.assertEqual(runtime['model_repository'], 'test/model')
                self.assertEqual(runtime['model_revision'], 'a'*40)
                self.assertFalse(runtime['confidential_computing'])
                self.assertFalse(runtime['attestation_verified'])
        asyncio.run(check())
        self.factory.assert_called_once_with(str(self.model), device='cuda', compute_type='float16', num_workers=1)
        self.assertFalse(self.api.health()['ready'])
        self.assertIsNone(self.api.health()['model'])

    def test_corrupted_weights_fail_before_decoder_construction(self):
        (self.model/'model.bin').write_bytes(b'changed weights')
        async def start():
            async with self.api.lifespan(self.api.app):
                self.fail('corrupted model must not start')
        with self.assertRaisesRegex(RuntimeError, 'hash mismatch'):
            asyncio.run(start())
        self.factory.assert_not_called()
        self.assertFalse(self.api.health()['ready'])

    def test_beam_five_vad_and_stateless_decoding_without_prompt_injection(self):
        decoder = Mock()
        decoder.transcribe.return_value = ([SimpleNamespace(start=0, end=1, text=' Testtext.')], SimpleNamespace(language='de', duration=1.0))
        self.api.model = decoder
        result = self.api.transcribe(b'test audio', 'de')
        self.assertEqual(result['text'], 'Testtext.')
        args, options = decoder.transcribe.call_args
        self.assertEqual(args[0].read(), b'test audio')
        self.assertEqual(options, {'language': 'de', 'beam_size': 5, 'vad_filter': True, 'condition_on_previous_text': False})

    def test_wrong_gpu_allocation_fails_before_model_load(self):
        async def start():
            async with self.api.lifespan(self.api.app):
                self.fail('wrong GPU allocation must not start')
        for count in (0, 2):
            self.cuda.get_cuda_device_count.return_value = count
            with self.assertRaisesRegex(RuntimeError, 'exactly one'):
                asyncio.run(start())
        self.factory.assert_not_called()
