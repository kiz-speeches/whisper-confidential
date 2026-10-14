import hashlib,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'gpu'))
from verify_model import verify_model
class ModelIntegrity(unittest.TestCase):
    def test_changed_or_additional_model_data_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'model';root.mkdir();(root/'model.bin').write_bytes(b'expected model')
            inputs=Path(tmp)/'inputs.json'
            inputs.write_text(json.dumps({'model':{'files':[{'path':'model.bin','sha256':hashlib.sha256(b'expected model').hexdigest()}]}}))
            verify_model(root,inputs)
            (root/'model.bin').write_bytes(b'changed model')
            with self.assertRaisesRegex(RuntimeError,'hash mismatch'):verify_model(root,inputs)
            (root/'model.bin').write_bytes(b'expected model');(root/'preprocessor_config.json').write_text('{}')
            with self.assertRaisesRegex(RuntimeError,'Unexpected'):verify_model(root,inputs)
