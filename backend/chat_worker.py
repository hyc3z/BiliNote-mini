"""Detached worker for explicitly requested chat jobs; exits when queue is empty."""
import os
from pathlib import Path
import sys
import time
os.chdir(Path(__file__).resolve().parent)
from filelock import FileLock, Timeout
from app.services.replay_chat import jobs_db
from app.routers.note import run_note_task
from app.enmus.note_enums import DownloadQuality
from app.db.init_db import init_db

def main():
    init_db()
    with FileLock('data/chat-worker.lock',timeout=5):
        with jobs_db() as db:
            db.execute("UPDATE jobs SET state='PENDING' WHERE state='RUNNING'")
        from concurrent.futures import ThreadPoolExecutor
        from app.services.task_serial_executor import worker_count
        def consume():
            idle=0
            while idle<4:
                with jobs_db() as db:
                    db.execute('BEGIN IMMEDIATE')
                    row=db.execute("SELECT * FROM jobs WHERE state='PENDING' ORDER BY created_at LIMIT 1").fetchone()
                    if row:db.execute("UPDATE jobs SET state='RUNNING' WHERE task_id=?",(row['task_id'],))
                if not row:
                    idle+=1;time.sleep(.5);continue
                idle=0
                try:
                    run_note_task(row['task_id'],row['source'],'bilibili',DownloadQuality.medium,link=True,model_name=row['model_name'],provider_id=row['provider_id'],_format=['link'],style='minimal')
                    from app.services.library import get
                    state='SUCCESS' if get(row['task_id']) else 'FAILED'
                    error=None if state=='SUCCESS' else '处理失败，请查询任务状态'
                except Exception as exc:
                    state='FAILED';error=str(exc)
                from app.services.task_cancellation import cancelled,finish
                if cancelled(row['task_id']):state='CANCELLED';error='用户停止';finish(row['task_id'])
                with jobs_db() as db:db.execute('UPDATE jobs SET state=?,error=? WHERE task_id=?',(state,error,row['task_id']))
        with ThreadPoolExecutor(max_workers=worker_count()) as pool:
            futures=[pool.submit(consume) for _ in range(worker_count())]
            for future in futures:future.result()

if __name__=='__main__':
    try:main()
    except Timeout:pass
