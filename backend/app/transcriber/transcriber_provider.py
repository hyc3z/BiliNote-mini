import os
import threading
from enum import Enum

class TranscriberType(str, Enum):
    FAST_WHISPER = "fast-whisper"

MLX_WHISPER_AVAILABLE = False
WhisperTranscriber = None
_transcribers = {TranscriberType.FAST_WHISPER: None}
_transcriber_configs = {TranscriberType.FAST_WHISPER: None}
_transcriber_init_lock = threading.Lock()

def get_whisper_transcriber(model_size="base", device="cpu", progress_callback=None):
    global WhisperTranscriber
    key = TranscriberType.FAST_WHISPER
    config = (model_size, device)
    with _transcriber_init_lock:
        if _transcriber_configs[key] != config or _transcribers[key] is None:
            if WhisperTranscriber is None:
                from app.transcriber.whisper import WhisperTranscriber as implementation
                WhisperTranscriber = implementation
            kwargs = {"model_size": model_size, "device": device}
            if progress_callback is not None:
                kwargs["progress_callback"] = progress_callback
            instance = WhisperTranscriber(**kwargs)
            _transcribers[key] = instance
            _transcriber_configs[key] = config
        return _transcribers[key]

def get_transcriber(transcriber_type="fast-whisper", model_size=None, device="cpu", progress_callback=None):
    if transcriber_type != "fast-whisper":
        raise ValueError("Mini 仅支持 faster-whisper 本地转录")
    return get_whisper_transcriber(model_size or os.getenv("WHISPER_MODEL_SIZE", "small"), device, progress_callback)
