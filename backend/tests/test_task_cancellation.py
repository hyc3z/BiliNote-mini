import json,os,tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from app.services import task_cancellation as c
from app.services.replay_chat import enqueue_parts,jobs_db
class CancelTasks(TestCase):
 def test_stops_queue_preserves_cache_and_scoped_execution_is_blocked(self):
  with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'NOTE_OUTPUT_DIR':folder+'/out','MINI_CHAT_JOBS_DB':folder+'/jobs.sqlite3','MINI_LIBRARY_DB':folder+'/notes.sqlite3'}):
   parts=[{'bvid':'BV1WHHy6pEqe','cid':str(i),'part':i+1,'source':'https://www.bilibili.com/video/BV1WHHy6pEqe','title':'test'} for i in range(2)]
   result=enqueue_parts(parts,model={'provider_id':'1','model_name':'test'},start=False)['parts'];ids=[p['task_id'] for p in result]
   with jobs_db() as db:db.execute("UPDATE jobs SET state='RUNNING' WHERE task_id=?",(ids[1],))
   cache=Path(folder)/'out'/f'{ids[0]}_transcript.txt';cache.write_text('原文')
   result=c.stop_all();self.assertEqual(result['cancelled'],1);self.assertEqual(result['stopping'],1)
   self.assertEqual(cache.read_text(),'原文')
   with self.assertRaises(c.TaskCancelled):
    with c.scope(ids[1]):pass
   with jobs_db() as db:self.assertEqual(db.execute("SELECT count(*) FROM jobs WHERE state='CANCELLED'").fetchone()[0],2)
   c.finish(ids[1]);self.assertEqual(json.loads((Path(folder)/'out'/f'{ids[1]}.status.json').read_text())['status'],'CANCELLED')
   c.clear(ids[0]);c.check(ids[0])
