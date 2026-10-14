import hashlib, json, sys, tomllib, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent/'tools'))
from policy import harden, initdata

class PolicyBinding(unittest.TestCase):
    def test_exact_toml_bytes_are_bound_and_recover_policy(self):
        policy='package agent_policy\ndefault ExecProcessRequest := false\n'
        raw, digest=initdata(policy)
        self.assertEqual(tomllib.loads(raw.decode())['data']['policy.rego'],policy)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
        self.assertNotEqual(initdata(policy.replace('false','true'))[1],digest)
        self.assertNotEqual(hashlib.sha256(raw+b'\n').hexdigest(),digest)

    def test_unreviewed_generator_format_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unexpected genpolicy'):
            harden('package agent_policy\ndefault CreateContainerRequest := true','image@sha256:bad')
