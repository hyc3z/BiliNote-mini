import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from app.services import video_selection as selection, replay_chat as chat

BV='BV1L4xJ62EvC'
OTHER='BV1234567890'
def video(count=3):
    return {'title':'教程','pages':[{'cid':101+i,'page':i+1,'part':f'第{i+1}课','duration':60+i} for i in range(count)]}

class VideoSelectionTests(unittest.TestCase):
    def test_full_bv_expands_all_pages_even_when_url_selects_one(self):
        with patch.object(selection,'api',return_value=video()):
            result=selection.inspect(f'https://www.bilibili.com/video/{BV}?p=2')
        self.assertEqual(result['count'],3)
        self.assertEqual(result['parts'][2]['source'],f'https://www.bilibili.com/video/{BV}?p=3')
        self.assertEqual(result['parts'][0]['key'],f'{BV}:101')

    def test_single_video_stays_selectable(self):
        with patch.object(selection,'api',return_value=video(1)):
            result=selection.inspect(BV)
        self.assertEqual(result['count'],1)

    def test_collection_expands_nested_pages_and_deduplicates(self):
        data=video(1)
        data['ugc_season']={'title':'合集','sections':[{'episodes':[{'bvid':BV},{'bvid':OTHER,'pages':video(2)['pages']},{'bvid':OTHER}]}]}
        with patch.object(selection,'api',return_value=data) as api:
            result=selection.inspect(BV)
        self.assertEqual(result['kind'],'collection');self.assertEqual(result['count'],3)
        self.assertEqual(api.call_count,1)
        self.assertEqual(result['parts'][-1]['source'],f'https://www.bilibili.com/video/{OTHER}?p=2')

    def test_multi_page_bv_does_not_unexpectedly_expand_whole_season(self):
        data=video(2);data['ugc_season']={'sections':[{'episodes':[{'bvid':OTHER}]}]}
        with patch.object(selection,'api',return_value=data):result=selection.inspect(BV)
        self.assertEqual(result['kind'],'pages');self.assertEqual(result['count'],2)

    def test_only_checked_entries_enter_durable_queue_in_source_order(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'MINI_CHAT_JOBS_DB':folder+'/jobs.sqlite3','MINI_LIBRARY_DB':folder+'/library.sqlite3','NOTE_OUTPUT_DIR':folder+'/out'}):
            with patch.object(selection,'api',return_value=video(32)),patch.object(chat,'start_worker') as start:
                result=selection.prepare(BV,[f'{BV}:103',f'{BV}:101'],{'provider_id':'1','model_name':'test'},start=False)
                repeated=selection.prepare(BV,[f'{BV}:101'],{'provider_id':'1','model_name':'test'},start=False)
            self.assertEqual([p['part'] for p in result['parts']],[1,3])
            self.assertEqual(result['parts'][0]['task_id'],repeated['parts'][0]['task_id'])
            with chat.jobs_db() as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],2)
            start.assert_not_called()

    def test_stale_or_forged_selection_is_rejected_before_enqueue(self):
        with patch.object(selection,'api',return_value=video()),patch.object(chat,'enqueue_parts') as enqueue:
            with self.assertRaises(ValueError):selection.prepare(BV,[f'{OTHER}:999'],{})
            enqueue.assert_not_called()

    def test_empty_batch_rejected(self):
        with self.assertRaises(ValueError):selection.prepare(BV,[],{})

    def test_714_parts_can_enter_queue_without_starting_processing(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'MINI_CHAT_JOBS_DB':folder+'/jobs.sqlite3','MINI_LIBRARY_DB':folder+'/library.sqlite3','NOTE_OUTPUT_DIR':folder+'/out'}):
            with patch.object(selection,'api',return_value=video(714)),patch.object(chat,'start_worker') as start:
                keys=[f'{BV}:{101+i}' for i in range(714)]
                result=selection.prepare(BV,keys,{'provider_id':'1','model_name':'test'},start=False)
                repeated=selection.prepare(BV,keys,{'provider_id':'1','model_name':'test'},start=False)
            self.assertEqual(len(result['parts']),714)
            self.assertEqual([p['task_id'] for p in result['parts']],[p['task_id'] for p in repeated['parts']])
            with chat.jobs_db() as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],714)
            start.assert_not_called()

    def test_invalid_bv_does_not_call_remote_api(self):
        with patch.object(selection,'api') as api:
            with self.assertRaises(ValueError):selection.inspect('not a video')
            api.assert_not_called()

if __name__=='__main__':unittest.main()
