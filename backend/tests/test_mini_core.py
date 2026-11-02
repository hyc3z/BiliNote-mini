"""Execute the real orchestration class with network/model/database boundaries mocked.

AST extraction isolates this unit from optional app startup dependencies; it does not
replace the methods under test. Full application integration is tested separately.
"""
import ast
import hashlib
import importlib.util
import json
import logging
import os
import pathlib
import tempfile
import types
import unittest
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]

def load_file(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

transcript_types = load_file('mini_transcript', 'app/models/transcriber_model.py')
audio_types = load_file('mini_audio', 'app/models/audio_model.py')
helper = load_file('mini_helper', 'app/utils/note_helper.py')
statuses = load_file('mini_status', 'app/enmus/task_status_enums.py')

@dataclass
class Result:
    markdown: str
    transcript: object
    audio_meta: object

class MiniCoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        source = ast.parse((ROOT / 'app/services/note.py').read_text(encoding='utf-8'))
        cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'NoteGenerator')
        isolated = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), cls], type_ignores=[])
        env = dict(json=json, hashlib=hashlib, os=os, Path=Path, asdict=asdict,
            NOTE_OUTPUT_DIR=self.folder, logger=logging.getLogger('mini-test'),
            TranscriptSegment=transcript_types.TranscriptSegment,
            TranscriptResult=transcript_types.TranscriptResult,
            AudioDownloadResult=audio_types.AudioDownloadResult, NoteResult=Result,
            get_preferences=lambda: {"device": "cpu"},
            TaskStatus=statuses.TaskStatus, DownloadQuality=types.SimpleNamespace(medium='medium'),
            normalize_video_url=lambda url: url.split('&tracking=')[0],
            resolve_bilibili_short_url=lambda url: url,
            prepend_source_link=helper.prepend_source_link,
            replace_content_markers=helper.replace_content_markers)
        exec(compile(ast.fix_missing_locations(isolated), str(ROOT / 'app/services/note.py'), 'exec'), env)
        self.Generator = env['NoteGenerator']
        config = Mock()
        config.get_whisper_model_size.return_value = 'small'
        config_module = types.ModuleType('app.services.transcriber_config_manager')
        config_module.TranscriberConfigManager = Mock(return_value=config)
        self.modules = patch.dict('sys.modules', {'app.services.transcriber_config_manager': config_module})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.transcript = transcript_types.TranscriptResult(language='zh', full_text='观点', segments=[transcript_types.TranscriptSegment(start=7425, end=7428, text='观点')])
        self.audio = audio_types.AudioDownloadResult(file_path='', title='直播', duration=8000, cover_url='', platform='bilibili', video_id='BV1234567890_p2', raw_info={})

    def test_subtitles_skip_model_and_download_and_share_part_cache(self):
        downloader = Mock()
        downloader.download_subtitles.return_value = self.transcript
        downloader.download.return_value = self.audio
        with patch.object(self.Generator, '_init_transcriber', side_effect=AssertionError('ASR must not load')), patch.object(self.Generator, '_get_downloader', return_value=downloader), patch.object(self.Generator, '_get_gpt'), patch.object(self.Generator, '_summarize_text', return_value='## 观点 *Content-[123:45]'), patch.object(self.Generator, '_save_metadata'):
            first = self.Generator().generate('https://www.bilibili.com/video/BV1234567890?p=2', 'bilibili', task_id='first', _format=['link'])
            self.assertIsNotNone(first)
            self.assertTrue(downloader.download.call_args.kwargs['skip_download'])
            downloader.download_video.assert_not_called()
            self.assertIn('?p=2&t=7425', first.markdown)
            self.assertIn('[02:03:45]', (self.folder / 'first_transcript.txt').read_text(encoding='utf-8'))
            downloader.download_subtitles.reset_mock()
            second = self.Generator().generate('https://www.bilibili.com/video/BV1234567890?p=2&tracking=x', 'bilibili', task_id='second')
            self.assertIsNotNone(second)
            downloader.download_subtitles.assert_not_called()
            third = self.Generator().generate('https://www.bilibili.com/video/BV1234567890?p=3', 'bilibili', task_id='third')
            self.assertIsNotNone(third)
            downloader.download_subtitles.assert_called_once()

    def test_no_subtitles_loads_asr_only_when_transcribing(self):
        generator = self.Generator()
        transcriber = Mock()
        transcriber.transcript.return_value = self.transcript
        with patch.object(generator, '_init_transcriber', return_value=transcriber) as initialize:
            self.assertIsNone(generator.transcriber)
            output = generator._transcribe_audio('sample.m4a', self.folder / 'task_transcript.json', statuses.TaskStatus.TRANSCRIBING)
            initialize.assert_called_once()
            self.assertEqual(output.full_text, '观点')
            self.assertEqual(transcriber.transcript.call_args.kwargs['file_path'], 'sample.m4a')
            self.assertTrue(callable(transcriber.transcript.call_args.kwargs['progress_callback']))

    def test_metadata_failure_never_falls_back_to_audio_download(self):
        downloader = Mock()
        downloader.download.side_effect = RuntimeError('offline')
        generator = self.Generator()
        with self.assertRaisesRegex(RuntimeError, '视频信息读取失败'):
            generator._download_media(downloader, 'url', 'medium', self.folder / 'task_audio.json', statuses.TaskStatus.DOWNLOADING, 'bilibili', None, False, False, 0, [], skip_download=True)
        self.assertEqual(downloader.download.call_count, 1)
        downloader.download_video.assert_not_called()

    def test_progress_updates_in_same_stage_and_resets_on_transition(self):
        generator = self.Generator()
        generator._update_status('progress', statuses.TaskStatus.PENDING)
        generator._update_status('progress', statuses.TaskStatus.TRANSCRIBING, percent=25, device='cpu', model='small')
        generator._update_status('progress', statuses.TaskStatus.TRANSCRIBING, percent=50)
        status_path = self.folder / 'progress.status.json'
        current = json.loads(status_path.read_text(encoding='utf-8'))
        self.assertEqual(current['percent'], 50)
        self.assertEqual(current['device'], 'cpu')
        start = current['started_at']
        generator._update_status('progress', statuses.TaskStatus.SUMMARIZING, message='分块总结')
        current = json.loads(status_path.read_text(encoding='utf-8'))
        self.assertNotIn('percent', current)
        self.assertNotIn('device', current)
        self.assertEqual(current['started_at'], start)

    def test_retry_resets_old_progress(self):
        generator = self.Generator()
        generator._update_status('retry', statuses.TaskStatus.TRANSCRIBING, percent=80)
        generator._update_status('retry', statuses.TaskStatus.FAILED, message='offline')
        generator._update_status('retry', statuses.TaskStatus.PENDING)
        current = json.loads((self.folder / 'retry.status.json').read_text(encoding='utf-8'))
        self.assertNotIn('percent', current)
        self.assertEqual(current['message'], '')

if __name__ == '__main__':
    unittest.main()
