"""Local searchable result storage, independent from browser history."""
import json
import os
from pathlib import Path
import sqlite3
from contextlib import contextmanager
import uuid

@contextmanager
def database():
    path = Path(os.getenv("MINI_LIBRARY_DB", "data/library.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE IF NOT EXISTS notes (task_id TEXT PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL, markdown TEXT NOT NULL, transcript TEXT NOT NULL, payload TEXT NOT NULL, saved_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        connection.execute("CREATE TABLE IF NOT EXISTS removed (task_id TEXT PRIMARY KEY)")
        yield connection
        connection.commit()
    finally:
        connection.close()

def save(task_id, payload):
    uuid.UUID(task_id)
    if not payload.get("markdown"):
        return
    audio = payload.get("audio_meta") or {}
    video_id = audio.get("video_id", "")
    source = (audio.get("raw_info") or {}).get("webpage_url") if audio.get("platform") in ("youtube","instagram") else "https://www.bilibili.com/video/" + video_id.replace("_p", "?p=")
    with database() as db:
        if db.execute("SELECT 1 FROM removed WHERE task_id=?", (task_id,)).fetchone():
            return
        db.execute("INSERT INTO notes(task_id,title,source,markdown,transcript,payload) VALUES(?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET title=excluded.title,source=excluded.source,markdown=excluded.markdown,transcript=excluded.transcript,payload=excluded.payload", (task_id, audio.get("title") or video_id or "回放笔记", source, payload["markdown"], (payload.get("transcript") or {}).get("full_text", ""), json.dumps(payload,ensure_ascii=False)))

def migrate(folder):
    for file in Path(folder).glob("*.json"):
        try:
            uuid.UUID(file.stem)
            save(file.stem, json.loads(file.read_text(encoding="utf-8")))
        except (ValueError, OSError, TypeError):
            continue

def search(query=""):
    with database() as db:
        term = "%" + query.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        rows = db.execute("SELECT task_id,title,source,saved_at,json_extract(payload, '$.audio_meta.duration') AS duration FROM notes WHERE title LIKE ? ESCAPE '!' OR markdown LIKE ? ESCAPE '!' OR source LIKE ? ESCAPE '!' OR COALESCE(json_extract(payload, '$.audio_meta.raw_info.owner.name'), '') LIKE ? ESCAPE '!' OR transcript LIKE ? ESCAPE '!' ORDER BY saved_at DESC,task_id DESC", (term,term,term,term,term)).fetchall()
        return [dict(row) for row in rows]

def get(task_id):
    with database() as db:
        row = db.execute("SELECT payload FROM notes WHERE task_id=?",(task_id,)).fetchone()
        return json.loads(row["payload"]) if row else None

def delete(task_id):
    uuid.UUID(task_id)
    with database() as db:
        db.execute("DELETE FROM notes WHERE task_id=?",(task_id,))
        db.execute("INSERT OR IGNORE INTO removed(task_id) VALUES(?)",(task_id,))
