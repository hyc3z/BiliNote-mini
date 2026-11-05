import os
import tempfile
import unittest
from unittest.mock import patch
from app.services import comments as c
BV='BV15sxS68EFq'
def item(n,likes=0,count=0):return {'rpid':n,'member':{'mid':str(n),'uname':'用户'},'content':{'message':'原评论'},'like':likes,'rcount':count,'ctime':1700000000}
class CommentTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        env=patch.dict(os.environ,{'MINI_COMMENTS_DB':temp.name+'/comments.sqlite3'});env.start();self.addCleanup(env.stop)
    def test_stats_do_not_conflate_root_and_child(self):
        stats=c.stats([c.pack(item(1,5)),c.pack(item(2,2),'1')])
        self.assertEqual((stats['count'],stats['roots'],stats['replies'],stats['likes']),(2,1,1,7))
    def test_snapshot_persistence(self):
        c.save(BV,{'state':'SUCCESS','comments':[c.pack(item(1))]})
        self.assertEqual(c.load(BV)['comments'][0]['id'],'1')
    def test_nested_replies_and_pinned_deduplication(self):
        def api(route,params):
            if route.endswith('view'):return {'aid':123}
            if route.endswith('/reply/reply'):return {'page':{'count':1},'replies':[item(2)]}
            return {'page':{'count':1},'top_replies':[item(1,3,1)],'replies':[item(1,3,1)]}
        data={'comments':[]}
        with patch.object(c,'api',side_effect=api):c.crawl(BV,data,{'limit':100,'sort':2,'replies':True})
        self.assertEqual([x['id'] for x in data['comments']],['1','2']);self.assertTrue(data['complete'])
    def test_count_limit_marks_incomplete(self):
        responses=[{'aid':123},{'page':{'count':50},'replies':[item(i) for i in range(1,21)]}]
        data={'comments':[]}
        with patch.object(c,'api',side_effect=responses):c.crawl(BV,data,{'limit':20,'sort':2,'replies':False})
        self.assertEqual(len(data['comments']),20);self.assertFalse(data['complete'])
    def test_pagination_failure_preserves_partial_results(self):
        responses=[{'aid':123},{'page':{'count':50},'replies':[item(1)]},RuntimeError('访问限制')]
        data={'comments':[]}
        with patch.object(c,'api',side_effect=responses),patch.object(c.time,'sleep'):
            with self.assertRaises(RuntimeError):c.crawl(BV,data,{'limit':100,'sort':2,'replies':False})
        self.assertEqual(len(data['comments']),1);self.assertFalse(data['complete'])
    def test_unknown_total_does_not_stop_after_first_short_page(self):
        data={'comments':[]}
        responses=[{'aid':123},{'page':{'count':0},'replies':[item(1)]},{'page':{'count':0},'replies':[item(2)]},{'page':{'count':0},'replies':[]}]
        with patch.object(c,'api',side_effect=responses),patch.object(c.time,'sleep'):
            c.crawl(BV,data,{'limit':100,'sort':2,'replies':False})
        self.assertEqual(len(data['comments']),2);self.assertFalse(data['complete']);self.assertTrue(data['warnings'])
    def test_repeated_page_stops_without_claiming_complete(self):
        data={'comments':[]}
        responses=[{'aid':123},{'page':{'count':1194},'replies':[item(1),item(2),item(3)]},{'page':{'count':0},'replies':[item(1),item(2),item(3)]}]
        with patch.object(c,'api',side_effect=responses),patch.object(c.time,'sleep'):
            c.crawl(BV,data,{'limit':100,'sort':2,'replies':True})
        self.assertEqual(data['total'],1194);self.assertEqual(len(data['comments']),3);self.assertFalse(data['complete']);self.assertIn('重复',data['message'])
    def test_cursor_pagination_uses_next_and_end_not_total_root_count(self):
        data={'comments':[]}
        responses=[{'aid':123},{'cursor':{'all_count':100,'next':7,'is_end':False},'replies':[item(1)]},{'cursor':{'all_count':100,'next':8,'is_end':True},'replies':[item(2)]}]
        with patch.object(c,'api',side_effect=responses) as api,patch.object(c.time,'sleep'):
            c.crawl(BV,data,{'limit':100,'sort':2,'replies':True})
        self.assertEqual(api.call_args_list[1].args[0],'x/v2/reply/main')
        self.assertEqual(api.call_args_list[2].args[1]['next'],7)
        self.assertEqual(len(data['comments']),2);self.assertTrue(data['complete'])
    def test_empty_reasoning_output_is_retried_not_merged(self):
        from types import SimpleNamespace as N
        from unittest.mock import Mock
        client=Mock()
        client.chat.completions.create.side_effect=[N(choices=[N(message=N(content='',reasoning_content='推理'),finish_reason='length')]),N(choices=[N(message=N(content='有效分析'),finish_reason='stop')])]
        self.assertEqual(c.completion_text(client,'test',[]),'有效分析')
        self.assertEqual(client.chat.completions.create.call_args.kwargs['max_tokens'],16384)
    def test_two_empty_outputs_raise_instead_of_succeed(self):
        from types import SimpleNamespace as N
        from unittest.mock import Mock
        client=Mock();client.chat.completions.create.return_value=N(choices=[N(message=N(content=''),finish_reason='stop')])
        with self.assertRaises(ValueError):c.completion_text(client,'test',[])
    def test_truncated_nonempty_output_is_not_accepted(self):
        from types import SimpleNamespace as N
        from unittest.mock import Mock
        client=Mock();client.chat.completions.create.return_value=N(choices=[N(message=N(content='不完整分析'),finish_reason='length')])
        with self.assertRaises(ValueError):c.completion_text(client,'test',[])
    def test_bad_bv_rejected(self):
        with self.assertRaises(ValueError):c.load('../secret')
if __name__=='__main__':unittest.main()
