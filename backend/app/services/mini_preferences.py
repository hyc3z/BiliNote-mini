import json
import os
from pathlib import Path

def get_preferences():
    path = Path("config/mini.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"device": data.get("device", os.getenv("WHISPER_DEVICE", "cpu"))}

def save_preferences(device):
    path = Path("config/mini.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"device": device}), encoding="utf-8")
