from faster_whisper import WhisperModel

from app.decorators.timeit import timeit
from app.models.transcriber_model import TranscriptSegment, TranscriptResult
from app.transcriber.base import Transcriber
from app.transcriber.whisper_models import (
    resolve_whisper_model,
    is_local_target,
    hf_cache_dirname,
)
from app.utils.logger import get_logger
from app.utils.path_helper import get_model_dir

from pathlib import Path
import os


'''
 Size of the model to use (tiny, tiny.en, base, base.en, small, small.en, distil-small.en, medium, medium.en, distil-medium.en, large-v1, large-v2, large-v3, large, distil-large-v2, distil-large-v3, large-v3-turbo, or turbo
'''
logger=get_logger(__name__)

# 历史遗留：之前用 modelscope 下载到自定义目录然后把路径传给 WhisperModel。
# 但 faster-whisper 1.1.1 的 download_model（utils.py:76）逻辑是：
# 只要 size_or_id 里含 "/" 就当 HF repo_id 处理，没有「本地目录直接返回」分支。
# 我们传 /app/models/whisper/whisper-tiny 进去 → 被当成不存在的 HF repo →
# 在线请求失败 → fallback local_files_only=True → HF cache 找不到（因为是
# modelscope 目录布局不是 HF）→ LocalEntryNotFoundError，误导说"离线模式"。
# 解法：彻底让 faster-whisper 自己处理下载——传 size name，配 download_root
# 作为 HF cache 根目录，HF_ENDPOINT 已经在 Dockerfile 里指到 hf-mirror.com，
# 国内能用。删掉 modelscope 那一套，避免布局不匹配。
class WhisperTranscriber(Transcriber):
    def __init__(
            self,
            model_size: str = "base",
            device: str = 'cpu',
            compute_type: str = None,
            cpu_threads: int = 1,
            progress_callback=None,
    ):
        from app.transcriber.cuda_runtime import configure_cuda_runtime
        configure_cuda_runtime()
        if device == 'cpu' or device is None:
            self.device = 'cpu'
        else:
            self.device = "cuda" if self.is_cuda() else "cpu"
            if device == 'cuda' and self.device == 'cpu':
                print('没有 cuda 使用 cpu进行计算')

        self.compute_type = compute_type or ("float16" if self.device == "cuda" else "int8")
        self.model_size = model_size

        model_dir = get_model_dir("whisper")
        from app.transcriber.model_transfer import ensure_model
        target = resolve_whisper_model(model_size)
        local = ensure_model(target, model_dir, model_size, progress_callback)
        if progress_callback:
            progress_callback(substage="loading_model", message="模型文件已就绪，正在加载到计算设备", model=model_size,
                requested_device=device, percent=None, downloaded_bytes=None, total_bytes=None)
        self.model = WhisperModel(model_size_or_path=local, device=self.device,
            compute_type=self.compute_type, local_files_only=True)

    @staticmethod
    def is_cuda() -> bool:
        try:
            import ctranslate2
            return ctranslate2.get_cuda_device_count() > 0
        except (ImportError, RuntimeError):
            return False

    @timeit
    def transcript(self, file_path: str, progress_callback=None) -> TranscriptResult:
        try:

            from app.services.terminology import scoped_terms
            hints='、'.join(scoped_terms())[:200]
            segments_raw, info = self.model.transcribe(file_path, language=None, vad_filter=True,
                initial_prompt=("可能涉及以下专有名词，仅在音频出现时使用："+hints) if hints else None, hotwords=hints or None)

            import time
            duration = float(info.duration or 0)
            last_report = 0.0
            def report(processed, finished=False):
                if progress_callback:
                    progress_callback(substage="transcribing", message="正在识别音频" if not finished else "转录完成，正在保存文字",
                        device=self.device, model=self.model_size, compute_type=self.compute_type,
                        processed_seconds=processed, total_seconds=duration,
                        percent=(100.0 if finished else min(99.9, processed / duration * 100)) if duration else None)
            report(0)
            segments = []
            full_text = ""

            for seg in segments_raw:
                if time.monotonic() - last_report >= 1:
                    report(min(float(seg.end), duration) if duration else float(seg.end))
                    last_report = time.monotonic()
                text = seg.text.strip()
                full_text += text + " "
                segments.append(TranscriptSegment(
                    start=seg.start,
                    end=seg.end,
                    text=text
                ))

            report(duration, finished=True)
            result= TranscriptResult(
                language=info.language,
                full_text=full_text.strip(),
                segments=segments,
                raw=None
            )
            # self.on_finish(file_path, result)
            return result
        except Exception as e:
            raise RuntimeError(f"转写失败：{e}") from e


