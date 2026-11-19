"""BiliNote Mini Windows tray host.

Starts the local FastAPI backend, keeps it in the notification area, and exposes
open/restart/autostart/exit actions. Run with ``--check`` for a headless smoke test.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path


APP_NAME = "BiliNote Mini"
PORT = int(os.getenv("BILINOTE_PORT", "8483"))
BASE_URL = f"http://127.0.0.1:{PORT}"
HEALTH_URL = f"{BASE_URL}/api/sys_check"
ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"
PYTHONW = BACKEND / ".venv" / "Scripts" / "pythonw.exe"
LOG_DIR = BACKEND / "logs"
RUN_DIR = BACKEND / ".run"
TRAY_LOG = LOG_DIR / "tray.log"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "BiliNoteMini"
ERROR_ALREADY_EXISTS = 183
CREATE_NO_WINDOW = 0x08000000

logger = logging.getLogger("bilinote.tray")


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(TRAY_LOG, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False


def message_box(text: str, title: str = APP_NAME) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)
    except Exception:
        print(f"{title}: {text}", file=sys.stderr)


def is_healthy(timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("code") == 0
    except (OSError, ValueError, urllib.error.URLError):
        return False


def wait_until_healthy(timeout: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_healthy():
            return True
        time.sleep(0.5)
    return False


def autostart_command() -> str:
    launcher = PYTHONW if PYTHONW.is_file() else PYTHON
    return f'"{launcher}" "{Path(__file__).resolve()}" --autostart'


def autostart_enabled() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
            return bool(value)
    except (ImportError, FileNotFoundError, OSError):
        return False


def set_autostart(enabled: bool) -> None:
    if os.name != "nt":
        return
    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


class BackendProcess:
    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.owned = False
        self._stdout = None
        self._stderr = None

    def start(self) -> bool:
        if is_healthy():
            logger.info("backend already healthy at %s; attaching without owning", BASE_URL)
            return True
        if not PYTHON.is_file():
            message_box(
                "找不到后端 Python 环境。\n\n"
                f"缺少：{PYTHON}\n请先运行安装脚本，或在项目目录执行安装步骤。"
            )
            return False

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        out_path = LOG_DIR / "tray-backend.out.log"
        err_path = LOG_DIR / "tray-backend.err.log"
        self._stdout = open(out_path, "a", encoding="utf-8", buffering=1)
        self._stderr = open(err_path, "a", encoding="utf-8", buffering=1)

        env = os.environ.copy()
        env.update(
            {
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
                "BACKEND_HOST": "127.0.0.1",
                "BACKEND_PORT": str(PORT),
            }
        )
        flags = CREATE_NO_WINDOW if os.name == "nt" else 0
        logger.info("starting backend: %s main.py", PYTHON)
        self.process = subprocess.Popen(
            [str(PYTHON), "-u", "main.py"],
            cwd=str(BACKEND),
            env=env,
            stdout=self._stdout,
            stderr=self._stderr,
            creationflags=flags,
        )
        self.owned = True
        try:
            (RUN_DIR / "backend.pid").write_text(str(self.process.pid), encoding="ascii")
        except OSError:
            logger.exception("could not write backend pid file")
        if wait_until_healthy():
            logger.info("backend ready (pid=%s)", self.process.pid)
            return True
        logger.error("backend did not become healthy; see %s", err_path)
        self.stop()
        message_box(
            "BiliNote 后端没有启动成功。\n\n"
            f"请查看日志：\n{err_path}\n\n"
            "常见原因：依赖未安装、端口被占用，或首次启动较慢。"
        )
        return False

    def stop(self) -> None:
        process = self.process
        if not process or not self.owned:
            self._close_logs()
            return
        logger.info("stopping backend pid=%s", process.pid)
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                process.terminate()
            process.wait(timeout=8)
        except Exception:
            logger.exception("failed to stop backend")
        self.process = None
        self.owned = False
        try:
            (RUN_DIR / "backend.pid").unlink(missing_ok=True)
        except OSError:
            pass
        self._close_logs()

    def restart(self) -> bool:
        self.stop()
        time.sleep(0.8)
        return self.start()

    def _close_logs(self) -> None:
        for stream in (self._stdout, self._stderr):
            try:
                if stream:
                    stream.close()
            except Exception:
                pass
        self._stdout = None
        self._stderr = None


def acquire_single_instance():
    if os.name != "nt":
        return True
    try:
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\BiliNoteMiniTray")
        if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            return None
        return handle
    except Exception:
        return True


def make_icon():
    try:
        import pystray
        from PIL import Image

        icon_path = Path(__file__).resolve().parent / "assets" / "bilinote.ico"
        image = Image.open(icon_path)
        return pystray.Icon("bilinote-mini", image, f"{APP_NAME} · 已就绪", menu=())
    except Exception as exc:
        message_box(f"托盘图标加载失败：{exc}")
        raise


def _menu():
    import pystray

    app = App.instance
    return pystray.Menu(
        pystray.MenuItem("打开工作台", app.open_workbench, default=True),
        pystray.MenuItem("打开数据目录", app.open_data),
        pystray.MenuItem("打开日志", app.open_logs),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("重启后端", app.restart_backend),
        pystray.MenuItem("开机自启动", app.toggle_autostart, checked=lambda item: autostart_enabled()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出 BiliNote", app.quit),
    )


class App:
    instance = None

    def __init__(self, icon) -> None:
        self.icon = icon
        self.backend = BackendProcess()
        App.instance = self

    def open_workbench(self, icon=None, item=None) -> None:
        webbrowser.open(BASE_URL)

    def open_data(self, icon=None, item=None) -> None:
        self._open_folder(BACKEND / "data")

    def open_logs(self, icon=None, item=None) -> None:
        self._open_folder(LOG_DIR)

    @staticmethod
    def _open_folder(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(path))
            else:
                webbrowser.open(path.as_uri())
        except OSError as exc:
            message_box(f"无法打开目录：{path}\n{exc}")

    def restart_backend(self, icon=None, item=None) -> None:
        if not self.backend.owned:
            if is_healthy():
                message_box("当前后端不是由托盘启动的，请在原进程里重启。")
                return
        if self.backend.restart():
            self.icon.notify("后端已重启", APP_NAME)
        else:
            self.icon.notify("后端重启失败，请查看日志", APP_NAME)

    def toggle_autostart(self, icon=None, item=None) -> None:
        try:
            set_autostart(not autostart_enabled())
        except OSError as exc:
            message_box(f"无法修改开机自启动：{exc}")
            return
        self.icon.update_menu()

    def quit(self, icon=None, item=None) -> None:
        self.backend.stop()
        self.icon.stop()


def run_check() -> int:
    backend = BackendProcess()
    ok = backend.start()
    if ok:
        print(f"OK {BASE_URL}")
    else:
        print("FAILED", file=sys.stderr)
    backend.stop()
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--autostart", action="store_true", help="started by Windows at login")
    parser.add_argument("--open", action="store_true", help="open the workbench after startup")
    parser.add_argument("--check", action="store_true", help="start backend, check health, stop, exit")
    args = parser.parse_args()

    setup_logging()
    if args.check:
        return run_check()

    if acquire_single_instance() is None:
        message_box("BiliNote Mini 已经在运行。")
        return 0

    icon = make_icon()
    app = App(icon)
    icon.menu = _menu()
    icon.update_menu()
    if not app.backend.start():
        app.backend.stop()
        return 1

    def on_setup(icon):
        icon.visible = True
        logger.info("tray icon registered")
        try:
            icon.notify("BiliNote Mini 已启动，托盘图标可在任务栏 ^ 溢出区找到。", APP_NAME)
        except Exception:
            logger.exception("tray notification failed")
        if args.open:
            # Opening the browser can block on some shell configurations; do it
            # only after the tray icon is registered, never before icon.run().
            try:
                app.open_workbench()
            except Exception:
                logger.exception("failed to open workbench")

    logger.info("starting tray icon loop")
    icon.run(setup=on_setup)
    app.backend.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
