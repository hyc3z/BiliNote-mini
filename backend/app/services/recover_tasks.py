import json
import time
from pathlib import Path

def recover_interrupted_tasks(folder):
    protected = set()
    queued=[]
    worker_alive=False
    try:
        from app.services.replay_chat import jobs_db, ROOT
        from filelock import FileLock, Timeout
        try:
            with FileLock(str(ROOT/'data/chat-worker.lock'),timeout=0):pass
        except Timeout:worker_alive=True
        with jobs_db() as db:
            queued=[dict(row) for row in db.execute("SELECT task_id,state FROM jobs WHERE state IN ('PENDING','RUNNING')") if (Path(folder)/f"{row['task_id']}.status.json").exists()]
            protected={row['task_id'] for row in queued}
            if not worker_alive:
                for row in queued:
                    if row['state']=='RUNNING':db.execute("UPDATE jobs SET state='PENDING' WHERE task_id=? AND state='RUNNING'",(row['task_id'],))
        for row in queued:
            if row['state']=='RUNNING' and worker_alive:continue
            path=Path(folder)/f"{row['task_id']}.status.json"
            try:
                record=json.loads(path.read_text(encoding='utf-8'))
                if record.get('status')=='FAILED' and record.get('message')!='上次处理被中断，已保留缓存，可以重试。':continue
                if record.get('status')=='SUCCESS':continue
                record.update(status='PENDING',message='已在持久队列中等待处理，缓存已保留',updated_at=time.time())
                temporary=path.with_suffix('.queue.tmp');temporary.write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8');temporary.replace(path)
            except (OSError,ValueError):pass
    except (ImportError,OSError):pass
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

    if queued and not worker_alive:
        from app.services.replay_chat import start_worker
        start_worker()
