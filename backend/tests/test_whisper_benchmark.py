"""Opt-in hardware benchmark: BENCHMARK_WHISPER=1 python -m unittest tests.test_whisper_benchmark -v."""
import gc
import json
import os
from pathlib import Path
import time
import unittest

@unittest.skipUnless(os.getenv('BENCHMARK_WHISPER')=='1','Real CPU/GPU benchmark is opt-in')
class WhisperBenchmark(unittest.TestCase):
    def test_latest_video_cpu_gpu(self):
        from app.services import library
        from app.transcriber.cuda_runtime import configure_cuda_runtime
        configure_cuda_runtime()
        from faster_whisper import WhisperModel
        from faster_whisper.audio import decode_audio
        import ctranslate2
        self.assertGreater(ctranslate2.get_cuda_device_count(),0,'No NVIDIA GPU available')
        note=library.get(library.search()[0]['task_id']);meta=note['audio_meta']
        source=Path(meta['file_path'])
        self.assertTrue(source.is_file(),f'Audio not cached: {source}')
        candidates=list(Path('models/whisper/mini-models').glob('models--*large-v3-turbo*/**/model.bin'))
        self.assertTrue(candidates,'large-v3-turbo must already be cached')
        model_path=candidates[0].parent
        seconds=int(os.getenv('BENCHMARK_SECONDS','60'))
        began=time.perf_counter();audio=decode_audio(str(source),sampling_rate=16000)[:seconds*16000];decode=time.perf_counter()-began
        duration=len(audio)/16000
        report={'video_id':meta['video_id'],'title':meta['title'],'audio':str(source),'sample_seconds':duration,'decode_seconds':decode,'model':'large-v3-turbo','beam_size':5,'cpu_threads':min(8,os.cpu_count() or 1),'runs':[]}
        for device,precision in [('cpu','int8'),('cuda','float16')]:
            print(f'Loading {device} ({precision})',flush=True)
            start=time.perf_counter();model=WhisperModel(str(model_path),device=device,compute_type=precision,cpu_threads=report['cpu_threads'],num_workers=1,local_files_only=True);load=time.perf_counter()-start
            # Consume generators fully: creating transcribe() alone does not run inference.
            list(model.transcribe(audio[:5*16000],language='zh',beam_size=5,vad_filter=True)[0])
            start=time.perf_counter();segments=list(model.transcribe(audio,language='zh',beam_size=5,vad_filter=True)[0]);elapsed=time.perf_counter()-start
            self.assertTrue(segments,'No transcript generated')
            row={'device':device,'precision':precision,'load_seconds':load,'transcribe_seconds':elapsed,'realtime_factor':elapsed/duration,'audio_seconds_per_second':duration/elapsed,'segment_count':len(segments),'text':''.join(s.text for s in segments)}
            report['runs'].append(row);print(json.dumps({k:v for k,v in row.items() if k!='text'},ensure_ascii=False),flush=True)
            del model;gc.collect()
        report['gpu_speedup']=report['runs'][0]['transcribe_seconds']/report['runs'][1]['transcribe_seconds']
        output=Path('.build-tmp/whisper-benchmark.json');output.parent.mkdir(exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('GPU speedup:',round(report['gpu_speedup'],2),'report:',output,flush=True)

if __name__=='__main__':unittest.main()

