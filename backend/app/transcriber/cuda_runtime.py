"""Discover optional NVIDIA wheel DLLs inside the project virtual environment."""
import os
from pathlib import Path
import sys

_handles = []

def configure_cuda_runtime():
    if os.name != "nt":
        return
    base = Path(sys.prefix) / "Lib/site-packages/nvidia"
    paths = []
    for package in ("cublas", "cudnn", "cuda_nvrtc"):
        for child in ("bin", "lib"):
            folder = base / package / child
            if folder.is_dir():
                paths.append(str(folder))
                _handles.append(os.add_dll_directory(str(folder)))
    if paths:
        os.environ["PATH"] = os.pathsep.join(paths + [os.environ.get("PATH", "")])
