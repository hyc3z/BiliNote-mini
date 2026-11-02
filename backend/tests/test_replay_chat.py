import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
from app.services import replay_chat as chat, library

class ReplayChatTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        folder=Path(self.temp.name)
        env=patch.dict(os.environ,{'MINI_LIBRARY_DB':str(folder/'library.sqlite3'),'MINI_CHAT_JOBS_DB':str(folder/'jobs.sqlite3'),'NOTE_OUTPUT_DIR':str(folder/'output')})
        env.start();self.addCleanup(env.stop)
        self.identifier=str(uuid.uuid4())
        self.bvid='BV1L4xJ62EvC'
        self.payload={'markdown':'观点','transcript':{'full_text':'显卡'},'audio_meta':{'title':'极客湾 2026-10-31 直播回放','video_id':self.bvid,'raw_info':{'uploader_id':chat.UPLOADER,'cid':101}}}
        library.save(self.identifier,self.payload)

    def test_title_date_is_not_upload_date(self):
        self.assertEqual(chat.title_date('极客湾 2026-10-31 回放 上传于11月1日'),'2026-10-31')
        self.assertEqual(chat.title_date('极客湾2026年10月31日直播'),'2026-10-31')
        self.assertIsNone(chat.title_date('2026-99-99'))

    def test_parts_expand_to_cids(self):
        data={'title':'直播','pages':[{'cid':101,'page':1,'part':'p1'},{'cid':102,'page':2,'part':'p2'}]}
        with patch.object(chat,'api',return_value=data):parts=chat.parts(self.bvid)
        self.assertEqual([p['cid'] for p in parts],['101','102'])
        self.assertTrue(parts[1]['source'].endswith('?p=2'))

    def test_enqueue_reuses_saved_parts_and_deduplicates_pending_jobs(self):
        parts=[{'bvid':self.bvid,'cid':str(101+i),'part':i+1,'title':'直播','source':f'https://www.bilibili.com/video/{self.bvid}?p={i+1}'} for i in range(2)]
        with patch.object(chat,'parts',return_value=parts),patch.object(chat,'default_model',return_value={'provider_id':'test','model_name':'test'}),patch.object(chat,'start_worker') as start:
            first=chat.enqueue([self.bvid],start=False)
            second=chat.enqueue([self.bvid],start=False)
        self.assertEqual(first['parts'][0]['state'],'SUCCESS')
        self.assertEqual(first['parts'][1]['state'],'PENDING')
        self.assertEqual(first['parts'][1]['task_id'],second['parts'][1]['task_id'])
        with chat.jobs_db() as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)
        start.assert_not_called()

    def test_discovery_reports_network_failure_and_keeps_local_notes(self):
        with patch.object(chat,'space_videos',side_effect=RuntimeError('访问限制')):
            result=chat.discover('2026-10-31')
        self.assertEqual(result['replays'][0]['bvid'],self.bvid)
        self.assertFalse(result['online_checked'])
        self.assertEqual(result['completeness'],'not_guaranteed')
        self.assertTrue(result['warning'])

    def test_worker_consumes_persisted_queue_without_a_web_server(self):
        import chat_worker
        folder=Path(self.temp.name)
        (folder/'data').mkdir()
        part={'bvid':self.bvid,'cid':'999','part':4,'title':'最后一P','source':f'https://www.bilibili.com/video/{self.bvid}?p=4'}
        with patch.object(chat,'parts',return_value=[part]),patch.object(chat,'default_model',return_value={'provider_id':'fake','model_name':'fake'}):
            queued=chat.enqueue([self.bvid],start=False)
        task_id=queued['parts'][0]['task_id']
        def fake_run(identifier,*args,**kwargs):
            payload={'markdown':'后台结果','transcript':{'full_text':'test'},'audio_meta':{'title':'最后一P','video_id':self.bvid+'_p4','raw_info':{'cid':999}}}
            library.save(identifier,payload)
        previous=Path.cwd()
        try:
            os.chdir(folder)
            with patch.object(chat_worker,'run_note_task',side_effect=fake_run),patch.object(chat_worker,'init_db'),patch.object(chat_worker.time,'sleep'):
                chat_worker.main()
        finally:
            os.chdir(previous)
        with chat.jobs_db() as db:
            self.assertEqual(db.execute('SELECT state FROM jobs WHERE task_id=?',(task_id,)).fetchone()[0],'SUCCESS')
        self.assertEqual(library.get(task_id)['markdown'],'后台结果')

if __name__=='__main__':unittest.main()
