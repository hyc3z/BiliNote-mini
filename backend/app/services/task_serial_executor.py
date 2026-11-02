import os
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Callable


class ConcurrentTaskExecutor:
    """Mini 使用单工作线程依次处理任务，避免并发加载转录模型。"""

    def __init__(self, max_workers: int | None = None):
        self._max_workers = max_workers or int("1")
        self._pool = ThreadPoolExecutor(max_workers=self._max_workers)

    def run(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        def guarded():
            from pathlib import Path
            from filelock import FileLock
            folder=Path(__file__).resolve().parents[2]/'data'
            folder.mkdir(exist_ok=True)
            with FileLock(str(folder/'processing.lock')):
                return fn(*args, **kwargs)
        future: Future = self._pool.submit(guarded)
        return future.result()

    def shutdown(self, wait: bool = True):
        self._pool.shutdown(wait=wait)


# 保持向后兼容的导出名
SerialTaskExecutor = ConcurrentTaskExecutor
task_serial_executor = ConcurrentTaskExecutor()
