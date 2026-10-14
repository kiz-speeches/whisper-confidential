"""Synthetic OCI integrity tests, not container or hardware verification."""
import hashlib,io,json,subprocess,tarfile,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
class Integrity(unittest.TestCase):
    def archive(self,path,tamper=False):
        files={}
        def add(value):
            raw=json.dumps(value).encode() if not isinstance(value,bytes) else value
            sha=hashlib.sha256(raw).hexdigest();files['blobs/sha256/'+sha]=raw
            return {'digest':'sha256:'+sha,'size':len(raw)}
        config=add({'architecture':'amd64','os':'linux','rootfs':{'type':'layers','diff_ids':[]}})
        layer=add(b'synthetic layer')
        manifest=add({'schemaVersion':2,'config':config,'layers':[layer]})
        files['index.json']=json.dumps({'schemaVersion':2,'manifests':[{**manifest,'platform':{'os':'linux','architecture':'amd64'}}]}).encode()
        if tamper:files['blobs/sha256/'+layer['digest'][7:]]=b'tampered layer!'
        with tarfile.open(path,'w') as tar:
            for name,raw in files.items():
                item=tarfile.TarInfo(name);item.size=len(raw);tar.addfile(item,io.BytesIO(raw))
        return manifest['digest']
    def test_valid_blob_hashes_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'image.tar';expected=self.archive(path)
            run=subprocess.run(['python3',str(ROOT/'tools/release.py'),'image-digest',str(path)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr);self.assertEqual(run.stdout.strip(),expected)
    def test_corrupted_layer_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'image.tar';self.archive(path,True)
            run=subprocess.run(['python3',str(ROOT/'tools/release.py'),'image-digest',str(path)],capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0);self.assertIn('OCI blob',run.stderr)
