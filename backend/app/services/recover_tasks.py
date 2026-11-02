import json
import time
from pathlib import Path

def recover_interrupted_tasks(folder):
    protected = set()
    try:
        from app.services.replay_chat import jobs_db, ROOT
        from filelock import FileLock, Timeout
        try:
            with FileLock(str(ROOT/'data/chat-worker.lock'),timeout=0):
                pass
        except Timeout:
            with jobs_db() as db:
                protected={r[0] for r in db.execute("SELECT task_id FROM jobs WHERE state IN ('PENDING','RUNNING')")}
    except (ImportError,OSError):
        pass
    for path in Path(folder).glob("*.status.json"):
        if path.name.removesuffix('.status.json') in protected:
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("status") in ("SUCCESS", "FAILED"):
                continue
            previous = record.get("status")
            record.update(status="FAILED", message="上次处理被中断，已保留缓存，可以重试。", updated_at=time.time())
            if previous == "MODEL_DOWNLOADING" and record.get("model"):
                record["can_reset_model_download"] = True
            temporary = path.with_suffix(".recovery.tmp")
            temporary.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            temporary.replace(path)
        except (OSError, ValueError):
            continue
