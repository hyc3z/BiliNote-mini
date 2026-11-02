import importlib.util
from pathlib import Path
import tempfile
import unittest
from filelock import FileLock

spec = importlib.util.spec_from_file_location('mini_model_transfer', Path(__file__).resolve().parents[1] / 'app/transcriber/model_transfer.py')
transfer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transfer)

class TransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.blobs = self.root / 'models--Org--Model' / 'blobs'
        self.blobs.mkdir(parents=True)
        self.partial = self.blobs / 'abc.incomplete'
        self.partial.write_bytes(b'partial')
        self.complete = self.blobs / 'complete'
        self.complete.write_bytes(b'complete')

    def test_only_incomplete_files_are_removed(self):
        self.assertEqual(transfer.clean_incomplete(self.root, 'Org/Model'), 1)
        self.assertFalse(self.partial.exists())
        self.assertEqual(self.complete.read_bytes(), b'complete')

    def test_active_download_is_not_removed(self):
        lock = self.root / '.locks/models--Org--Model/abc.lock'
        lock.parent.mkdir(parents=True)
        with FileLock(str(lock)):
            with self.assertRaises(RuntimeError):
                transfer.clean_incomplete(self.root, 'Org/Model')
        self.assertTrue(self.partial.exists())

    def test_in_process_download_is_not_removed(self):
        with transfer._lock:
            with self.assertRaises(RuntimeError):
                transfer.clean_incomplete(self.root, 'Org/Model')
        self.assertTrue(self.partial.exists())

    def test_download_resumes_and_validates_then_works_offline(self):
        import hashlib
        from unittest.mock import patch
        payloads = {'config.json': b'config', 'model.bin': b'weight-data', 'tokenizer.json': b'tokenizer'}
        native = self.root / 'mini-models/models--Org--Model'
        native.mkdir(parents=True)
        (native / 'model.bin.incomplete').write_bytes(b'weight-')
        reports = []
        calls = []
        class Response:
            def __init__(self, content=b'', status=200, headers=None):
                self.content=content; self.status_code=status; self.headers=headers or {}
            def raise_for_status(self): pass
            def json(self):
                return {'sha':'revision','siblings':[{'rfilename': k,'size':len(v),'lfs':{'sha256':hashlib.sha256(v).hexdigest()}} for k,v in payloads.items()]}
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def iter_content(self, size): yield self.content
        def get(url, **kwargs):
            if '/api/models/' in url: return Response()
            name=url.rsplit('/',1)[1]
            value=kwargs['headers']['Range'].split('=')[1]
            start,end=map(int,value.split('-'))
            calls.append((name,start))
            return Response(payloads[name][start:end+1],206,{'Content-Range':f'bytes {start}-{end}/{len(payloads[name])}'})
        with patch('requests.get',side_effect=get), patch('huggingface_hub.snapshot_download',side_effect=RuntimeError('not cached')):
            local = transfer.ensure_model('Org/Model', self.root, 'test', lambda **d: reports.append(d))
        self.assertIn(('model.bin',7), calls)
        self.assertEqual((Path(local)/'model.bin').read_bytes(),payloads['model.bin'])
        self.assertTrue(any(p.get('downloaded_bytes') for p in reports))
        with patch('requests.get',side_effect=AssertionError('must not use network')):
            self.assertEqual(transfer.ensure_model('Org/Model',self.root,'test'),local)

    def test_native_partials_are_cleaned_without_removing_complete_weights(self):
        native = self.root / 'mini-models/models--Org--Model'
        native.mkdir(parents=True)
        (native/'model.bin.incomplete').write_bytes(b'broken')
        (native/'config.json').write_bytes(b'complete')
        self.assertEqual(transfer.clean_incomplete(self.root,'Org/Model'),2)
        self.assertTrue((native/'config.json').exists())

if __name__ == '__main__': unittest.main()
