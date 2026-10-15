"""Publication must wait until every release asset is uploaded and hash-checked."""
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import publish

class PublishTests(unittest.TestCase):
    def test_github_publication_uses_http_patch(self):
        with patch.object(publish.urllib.request,'urlopen') as open_url:
            open_url.return_value.__enter__.return_value=io.StringIO('{}')
            publish.github('releases/123','test-token',{'draft':False},method='PATCH')
        self.assertEqual(open_url.call_args.args[0].get_method(),'PATCH')

    def run_publication(self, failure=None):
        calls=[]
        def github(path, token, data=None, content_type='application/json', method=None):
            calls.append((path,data,method))
            if path=='releases':
                return {'id':123,'upload_url':'https://uploads.github.com/assets{?name}'}
            if path.startswith('https://uploads.github.com/'):
                if failure=='interrupted':raise OSError('Upload interrupted')
                return {'state':'uploaded','name':path.split('name=',1)[1],'size':len(data),
                        'digest':'sha256:'+('0'*64 if failure=='corrupt' else hashlib.sha256(data).hexdigest())}
            return {'draft':False,'prerelease':True,'html_url':'https://github.com/example/release'}
        with tempfile.TemporaryDirectory() as directory:
            files=[Path(directory)/name for name in ('release-manifest.json','SHA256SUMS')]
            for file in files:file.write_bytes(file.name.encode())
            with patch.object(publish,'github',side_effect=github):
                if failure:
                    with self.assertRaises((OSError,ValueError)):
                        publish.publish_release('test-token',{'version':'v0.3.0','git_commit':'a'*40},files)
                else:
                    result=publish.publish_release('test-token',{'version':'v0.3.0','git_commit':'a'*40},files)
                    self.assertFalse(result['draft'])
        return calls

    def test_publish_only_after_all_uploads(self):
        calls=self.run_publication()
        self.assertTrue(calls[0][1]['draft'])
        self.assertEqual(len(calls),4)
        self.assertTrue(all(c[0].startswith('https://uploads.github.com/') for c in calls[1:-1]))
        self.assertEqual(calls[-1],('releases/123',{'draft':False,'prerelease':True,'make_latest':'false'},'PATCH'))

    def test_interrupted_upload_is_not_published(self):
        self.assertFalse(any(call[2]=='PATCH' for call in self.run_publication('interrupted')))

    def test_corrupt_upload_is_not_published(self):
        self.assertFalse(any(call[2]=='PATCH' for call in self.run_publication('corrupt')))

if __name__=='__main__':unittest.main()
