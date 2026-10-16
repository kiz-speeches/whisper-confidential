"""Verify that every approved lookup resolves to an internally consistent proof."""
import hashlib
import json
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ApprovedReferences(unittest.TestCase):
    def test_approved_artifacts_match_measurements_and_each_other(self):
        catalog = json.loads((ROOT / 'verification/accepted.json').read_text())
        self.assertEqual(catalog['schema_version'], 1)
        self.assertGreater(len(catalog['entries']), 0)
        seen = set()
        for entry in catalog['entries']:
            key = (entry['measurement'], entry['host_data'])
            self.assertNotIn(key, seen, 'ambiguous approval')
            seen.add(key)
            self.assertRegex(key[0], r'^[a-f0-9]{96}$')
            self.assertRegex(key[1], r'^[a-f0-9]{64}$')
            self.assertRegex(entry['path'], r'^verification/releases/v[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?$')
            folder = ROOT / entry['path']
            reference = json.loads((folder / 'attestation-policy.json').read_text())
            initdata = (folder / 'initdata.toml').read_bytes()
            policy = (folder / 'policy.rego').read_bytes()
            self.assertEqual(reference['measurement'], key[0])
            self.assertEqual(reference['expected_host_data'], key[1])
            self.assertEqual(hashlib.sha256(initdata).hexdigest(), key[1])
            self.assertEqual(hashlib.sha256(policy).hexdigest(), reference['policy_sha256'])
            self.assertEqual(tomllib.loads(initdata.decode())['data']['policy.rego'].encode(), policy)
            self.assertRegex(reference['cpu_image'], r'@sha256:[a-f0-9]{64}$')
            self.assertIn('sources[0] == ' + json.dumps(reference['cpu_image']), policy.decode())
