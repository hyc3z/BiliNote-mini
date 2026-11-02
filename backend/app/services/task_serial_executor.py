"""Bounded pipeline concurrency with a cross-process transcription guard."""
import os
import time
from pathlib import Path
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from filelock import FileLock, Timeout

FOLDER = Path(__file__).resolve().parents[2] / 'data'

def worker_count():
    try:
        return max(1, min(6, int(os.getenv('MINI_TASK_CONCURRENCY', '3'))))
    except ValueError:
        return 3

@contextmanager
def pipeline_slot():
    FOLDER.mkdir(exist_ok=True)
    while True:
        for index in range(worker_count()):
            lock = FileLock(str(FOLDER / f'pipeline-{index}.lock'))
            try:
                lock.acquire(timeout=0)
            except Timeout:
                continue
            try:
                yield
            finally:
                lock.release()
            return
        time.sleep(.1)

def serial_transcription(fn):
    @wraps(fn)
    def guarded(*args, **kwargs):
        FOLDER.mkdir(exist_ok=True)
        with FileLock(str(FOLDER / 'transcription.lock')):
            return fn(*args, **kwargs)
    return guarded

class ConcurrentTaskExecutor:
    def __init__(self, max_workers=None):
        self._max_workers = worker_count() if max_workers is None else max_workers
        self._pool = ThreadPoolExecutor(max_workers=self._max_workers)

    def run(self, fn, *args, **kwargs):
        def guarded():
            with pipeline_slot():
                return fn(*args, **kwargs)
        return self._pool.submit(guarded).result()

    def shutdown(self, wait=True):
        self._pool.shutdown(wait=wait)

class SerialTaskExecutor(ConcurrentTaskExecutor):
    def __init__(self, max_workers=1):
        super().__init__(max_workers)

task_serial_executor = ConcurrentTaskExecutor()
