import tempfile,os
from unittest import TestCase
from unittest.mock import patch
from app.services import submission_batches as batches
from app.services.replay_chat import enqueue_parts
class SubmissionBatches(TestCase):
 def test_submission_membership_and_duplicate_reuse(self):
  with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'MINI_CHAT_JOBS_DB':folder+'/jobs.sqlite3','MINI_LIBRARY_DB':folder+'/notes.sqlite3','NOTE_OUTPUT_DIR':folder+'/out'}):
   parts=[{'bvid':'BV1WHHy6pEqe','cid':str(i),'part':i+1,'source':'https://www.bilibili.com/video/BV1WHHy6pEqe?p='+str(i+1),'title':'test'} for i in range(3)]
   result=enqueue_parts(parts,model={'provider_id':'1','model_name':'test'},start=False)['parts']
   first=batches.record('批次一',result);second=batches.record('批次二',result[:1])
   rows={b['id']:b for b in batches.list_batches()}
   self.assertEqual(len(rows[first]['task_ids']),3);self.assertEqual(len(rows[second]['task_ids']),1)
   self.assertFalse(rows[first]['inferred']);self.assertEqual(len(rows),2)
 def test_history_is_explicitly_inferred_and_stable(self):
  with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'MINI_CHAT_JOBS_DB':folder+'/jobs.sqlite3','MINI_LIBRARY_DB':folder+'/notes.sqlite3','NOTE_OUTPUT_DIR':folder+'/out'}):
   enqueue_parts([{'bvid':'BV1WHHy6pEqe','cid':'1','part':1,'source':'https://www.bilibili.com/video/BV1WHHy6pEqe','title':'test'}],model={'provider_id':'1','model_name':'test'},start=False)
   first=batches.list_batches();second=batches.list_batches()
   self.assertTrue(first[0]['inferred']);self.assertEqual(first,second)
