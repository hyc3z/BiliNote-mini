import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('mini_library',Path(__file__).resolve().parents[1]/'app/services/library.py')
library=importlib.util.module_from_spec(spec);spec.loader.exec_module(library)

class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'MINI_LIBRARY_DB':str(self.folder/'library.sqlite3')});self.env.start();self.addCleanup(self.env.stop)
        self.id=str(uuid.uuid4())
        self.payload={'markdown':'显卡性能观点','transcript':{'full_text':'能效测试 RTX 5070 100%','segments':[]},'audio_meta':{'title':'极客湾直播','video_id':'BVexample_p2','raw_info':{'owner':{'name':'测试UP'}}}}

    def test_search_title_summary_transcript_and_restore_payload(self):
        library.save(self.id,self.payload)
        for query in ('极客湾','性能','5070','100%','BVexample','测试UP'):
            self.assertEqual(library.search(query)[0]['task_id'],self.id)
        self.assertEqual(library.get(self.id),self.payload)
        self.assertEqual(library.search('_'),[])

    def test_delete_is_not_resurrected_by_startup_migration(self):
        (self.folder/f'{self.id}.json').write_text(json.dumps(self.payload),encoding='utf-8')
        library.migrate(self.folder)
        library.delete(self.id)
        library.migrate(self.folder)
        self.assertEqual(library.search(),[])
        self.assertIsNone(library.get(self.id))

    def test_repeated_save_updates_without_duplicate_rows(self):
        library.save(self.id,self.payload)
        self.payload['markdown']='新的观点'
        library.save(self.id,self.payload)
        self.assertEqual(len(library.search()),1)
        self.assertEqual(library.get(self.id)['markdown'],'新的观点')

if __name__=='__main__':unittest.main()
