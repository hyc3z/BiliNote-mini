import importlib.util
import pathlib
import threading
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "app" / "services" / "task_serial_executor.py"
spec = importlib.util.spec_from_file_location("task_serial_executor", MODULE_PATH)
if spec is None or spec.loader is None:
    raise ImportError("task_serial_executor module spec not found")
task_serial_executor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(task_serial_executor)
SerialTaskExecutor = task_serial_executor.SerialTaskExecutor


class TestTaskSerialExecutor(unittest.TestCase):
    def test_executor_runs_tasks_one_by_one(self):
        executor = SerialTaskExecutor()
        state_lock = threading.Lock()
        state = {"active": 0, "peak_active": 0}

        def critical_work():
            with state_lock:
                state["active"] += 1
                state["peak_active"] = max(state["peak_active"], state["active"])
            time.sleep(0.05)
            with state_lock:
                state["active"] -= 1

        threads = [threading.Thread(target=lambda: executor.run(critical_work)) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(state["peak_active"], 1)

    def test_parallel_tasks_overlap(self):
        executor = task_serial_executor.ConcurrentTaskExecutor(max_workers=2)
        barrier = threading.Barrier(2)
        def work():
            barrier.wait(timeout=3)
            return True
        from concurrent.futures import ThreadPoolExecutor
        try:
            with ThreadPoolExecutor(max_workers=2) as callers:
                futures=[callers.submit(executor.run,work) for _ in range(2)]
                self.assertTrue(all(f.result(timeout=5) for f in futures))
        finally:
            executor.shutdown()

    def test_transcription_is_serial_and_releases_after_error(self):
        state={'active':0,'peak':0}
        lock=threading.Lock()
        @task_serial_executor.serial_transcription
        def work(fail=False):
            with lock:
                state['active']+=1
                state['peak']=max(state['peak'],state['active'])
            try:
                time.sleep(.03)
                if fail:raise ValueError('expected')
            finally:
                with lock:state['active']-=1
        with self.assertRaises(ValueError):work(True)
        threads=[threading.Thread(target=work) for _ in range(3)]
        for t in threads:t.start()
        for t in threads:t.join(timeout=3)
        self.assertTrue(all(not t.is_alive() for t in threads))
        self.assertEqual(state['peak'],1)


if __name__ == "__main__":
    unittest.main()
