"""Locate an ffmpeg binary for yt-dlp.

Priority:
1. FFMPEG_LOCATION / FFMPEG_PATH environment variable;
2. a local backend/bin/ffmpeg.exe used for portable installs;
3. ffmpeg on PATH;
4. the binary bundled in the imageio-ffmpeg Python package (installed via requirements).
"""

import os
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Optional


@lru_cache(maxsize=1)
def get_ffmpeg_location() -> Optional[str]:
    override = os.getenv("FFMPEG_LOCATION") or os.getenv("FFMPEG_PATH")
    if override:
        path = Path(override).expanduser()
        if path.is_dir():
            candidate = path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
            if candidate.is_file():
                return str(candidate)
        elif path.is_file():
            return str(path)

    local = Path(__file__).resolve().parents[2] / "bin" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if local.is_file():
        return str(local)

    found = shutil.which("ffmpeg")
    if found:
        return found

    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).is_file():
            return bundled
    except Exception:
        pass
    return None
