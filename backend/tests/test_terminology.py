import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
from app.services import terminology, library

class TerminologyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root=Path(temp.name); self.id=str(uuid.uuid4())
        env=patch.dict(os.environ, {'NOTE_OUTPUT_DIR':str(self.root),'MINI_LIBRARY_DB':str(self.root/'library.sqlite3')}); env.start(); self.addCleanup(env.stop)
        self.data={'segments':[{'start':0,'end':2,'text':'骁龙815 比 1815 和8150好'}], 'full_text':'骁龙815 比 1815 和8150好','language':'zh','raw':{}}
        self.file=self.root/f'{self.id}_transcript.json'; self.file.write_text(json.dumps(self.data),encoding='utf-8')
        library.save(self.id,{'transcript':self.data,'markdown':'旧摘要','audio_meta':{'title':'测试'}})
    def test_preview_does_not_mutate_and_uses_boundaries(self):
        before=self.file.read_bytes(); result=terminology.correct(self.id,'815','8E5')
        self.assertEqual(result['matches'],1); self.assertEqual(result['examples'][0]['after'],'骁龙8E5 比 1815 和8150好')
        self.assertEqual(before,self.file.read_bytes()); self.assertFalse(list(self.root.glob('*.original.json')))
    def test_apply_preserves_original_and_marks_summary_stale(self):
        terminology.correct(self.id,'815','8E5',True)
        original=self.root/f'{self.id}_transcript.original.json'
        self.assertEqual(json.loads(original.read_text(encoding='utf-8')),self.data)
        note=library.get(self.id); self.assertTrue(note['summary_stale']); self.assertEqual(note['markdown'],'旧摘要')
        self.assertEqual(note['transcript']['raw']['corrections'][0]['to'],'8E5')
        terminology.correct(self.id,'8E5','8EE6',True)
        self.assertEqual(json.loads(original.read_text(encoding='utf-8')),self.data)
    def test_rejects_invalid_task_path(self):
        with self.assertRaises(ValueError): terminology.correct('../outside','815','8E5',True)

if __name__=='__main__':unittest.main()
