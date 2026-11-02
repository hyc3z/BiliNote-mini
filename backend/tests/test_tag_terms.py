import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from app.services import terminology as t

class TagTermsTests(unittest.TestCase):
    def setUp(self):
        self.old=os.getcwd()
        self.temp=tempfile.TemporaryDirectory()
        os.chdir(self.temp.name)
    def tearDown(self):
        os.chdir(self.old)
        self.temp.cleanup()
    def test_migration_binding_and_isolation(self):
        t.save_terms(['RTX 5070'])
        self.assertEqual(t.tag_config()['tags']['数码'],['RTX 5070'])
        self.assertEqual(t.scoped_terms(),[])
        t.update_tag_config(tag='音乐',items=['Daft Punk'])
        t.update_tag_config(bvid='BV1Qub56eEYj',tags=['数码'])
        t.update_tag_config(bvid='BV14xJ62EvCc',tags=['音乐'])
        class Reader:
            @t.with_video_terms
            def generate(self,video_url):return t.scoped_terms()
        reader=Reader()
        with ThreadPoolExecutor(2) as pool:
            first=pool.submit(reader.generate,'BV1Qub56eEYj')
            second=pool.submit(reader.generate,'BV14xJ62EvCc')
            self.assertEqual(first.result(),['RTX 5070'])
            self.assertEqual(second.result(),['Daft Punk'])
        self.assertEqual(t.scoped_terms(),[])
    def test_validation(self):
        with self.assertRaises(ValueError):t.update_tag_config(tag='x',items=['a'*201])
        with self.assertRaises(ValueError):t.update_tag_config(bvid='BV1Qub56eEYj',tags=['missing'])
