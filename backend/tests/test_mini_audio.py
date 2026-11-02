import ast
import os
import pathlib
import tempfile
import types
import unittest
from unittest.mock import Mock

ROOT = pathlib.Path(__file__).resolve().parents[1]

class AudioDownloadTests(unittest.TestCase):
    def test_original_audio_without_ffmpeg(self):
        self.check(False)

    def test_metadata_does_not_download(self):
        self.check(True)

    def check(self, metadata_only):
        tree = ast.parse((ROOT / 'app/downloaders/bilibili_downloader.py').read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'BilibiliDownloader')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'download')
        module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), method], type_ignores=[])
        options = []
        with tempfile.TemporaryDirectory() as temp:
            audio = pathlib.Path(temp) / 'BVexample.m4a'
            if not metadata_only: audio.write_bytes(b'audio fixture')
            class FakeYDL:
                def __init__(self, opts): options.append(opts)
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def extract_info(self, url, download):
                    assert download is not metadata_only
                    return {'id': 'BVexample', 'title': 'test', 'duration': 3, 'ext': 'm4a'}
                def prepare_filename(self, info): return str(audio)
            env = {'os': os, 'yt_dlp': types.SimpleNamespace(YoutubeDL=FakeYDL), 'YDL_RETRY_OPTS': {}, 'AudioDownloadResult': lambda **kw: types.SimpleNamespace(**kw)}
            exec(compile(ast.fix_missing_locations(module), '<actual downloader method>', 'exec'), env)
            result = env['download'](types.SimpleNamespace(_cookiefile=None, _report_progress=lambda event: None), 'https://www.bilibili.com/video/BVexample', output_dir=temp, skip_download=metadata_only)
            self.assertEqual(options[0]['postprocessors'], [])
            self.assertEqual(result.file_path, '' if metadata_only else str(audio))
            self.assertNotIn('best', options[0]['format'].split('/'))

if __name__ == '__main__': unittest.main()
