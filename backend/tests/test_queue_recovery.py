import tempfile,json,os
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from app.services.replay_chat import enqueue_parts,jobs_db
from app.services.recover_tasks import recover_interrupted_tasks
class QueueRecovery(TestCase):
 def test_pending_job_is_not_failed_and_false_failure_is_repaired(self):
  with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'MINI_CHAT_JOBS_DB':folder+'/jobs.sqlite3','MINI_LIBRARY_DB':folder+'/notes.sqlite3','NOTE_OUTPUT_DIR':folder+'/out'}):
   part={'bvid':'BV1WHHy6pEqe','cid':'123','part':1,'source':'https://www.bilibili.com/video/BV1WHHy6pEqe','title':'test'}
   job=enqueue_parts([part],model={'provider_id':'1','model_name':'test'},start=False)['parts'][0]
   file=Path(folder)/'out'/f"{job['task_id']}.status.json"
   file.write_text(json.dumps({'status':'FAILED','message':'上次处理被中断，已保留缓存，可以重试。'}),encoding='utf-8')
   with patch('app.services.replay_chat.start_worker'),patch('filelock.FileLock'):
    recover_interrupted_tasks(file.parent)
   self.assertEqual(json.loads(file.read_text(encoding='utf-8'))['status'],'PENDING')
   with jobs_db() as db:self.assertEqual(db.execute('select state from jobs').fetchone()[0],'PENDING')
