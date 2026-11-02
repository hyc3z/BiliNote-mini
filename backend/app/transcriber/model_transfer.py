"""Explicit model acquisition and conservative removal of incomplete downloads."""
from pathlib import Path
import threading

_lock = threading.Lock()
FILES = ["config.json", "model.bin", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"]

class ModelDownloadError(RuntimeError):
    can_reset_model_download = True
    def __init__(self, model_size, message):
        self.model_size = model_size
        super().__init__(message)

def clean_incomplete(cache_root, repo_id):
    from filelock import FileLock, Timeout
    from contextlib import ExitStack
    root = Path(cache_root).resolve()
    name = "models--" + repo_id.replace("/", "--")
    folder = (root / name / "blobs").resolve()
    if not folder.is_relative_to(root):
        raise ValueError("模型缓存路径无效")
    if not _lock.acquire(blocking=False):
        raise RuntimeError("模型正在下载，不能清理；请等待任务结束")
    try:
        candidates = list(folder.glob("*.incomplete")) if folder.is_dir() else []
        native = (root / "mini-models" / name).resolve()
        if not native.is_relative_to(root):
            raise ValueError("模型缓存路径无效")
        if native.is_dir():
            candidates.extend(native.glob("*.incomplete"))
        with ExitStack() as stack:
            if native.is_dir():
                try:
                    stack.enter_context(FileLock(str(native / ".download.lock"), timeout=0))
                except Timeout as exc:
                    raise RuntimeError("模型仍在下载，不能清理") from exc
            for candidate in candidates:
                if candidate.is_symlink() or not candidate.resolve().is_relative_to(root):
                    raise ValueError("不允许清理缓存外的文件")
                lock_path = root / ".locks" / name / (candidate.name.removesuffix(".incomplete") + ".lock")
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                try:
                    stack.enter_context(FileLock(str(lock_path), timeout=0))
                except Timeout as exc:
                    raise RuntimeError("模型文件仍被下载进程占用，无法清理") from exc
            for candidate in candidates:
                candidate.unlink(missing_ok=True)
        return len(candidates)
    finally:
        _lock.release()

def ensure_model(target, cache_root, model_size, callback=None):
    import requests
    import json
    import fnmatch
    import hashlib
    import time
    from huggingface_hub import snapshot_download
    from filelock import FileLock
    def report(**details):
        if callback:
            callback(model=model_size, substage="downloading_model", **details)
    if Path(target).is_dir():
        return target
    sources = ["https://huggingface.co", "https://hf-mirror.com"]
    folder = (Path(cache_root) / "mini-models" / ("models--" + target.replace("/", "--"))).resolve()
    if not folder.is_relative_to(Path(cache_root).resolve()):
        raise ValueError("模型缓存路径无效")
    folder.mkdir(parents=True, exist_ok=True)
    with _lock, FileLock(str(folder / ".download.lock"), timeout=0):
        index = folder / "model_index.json"
        try:
            cached = json.loads(index.read_text(encoding="utf-8"))
            if cached.get("repo") == target and all((folder / entry["name"]).is_file() and (folder / entry["name"]).stat().st_size == entry["size"] for entry in cached["files"]):
                return str(folder)
        except (OSError, ValueError, KeyError):
            pass
        try:
            local = snapshot_download(target, cache_dir=cache_root, local_files_only=True)
            if all((Path(local) / f).is_file() and (Path(local) / f).stat().st_size > 0 for f in ("model.bin", "config.json", "tokenizer.json")):
                return local
        except Exception:
            pass
        try:
            manifest = None
            for base in sources:
                report(message="正在连接模型仓库", download_source=base, percent=None)
                try:
                    response = requests.get(base + "/api/models/" + target + "?blobs=true", timeout=(5, 12))
                    response.raise_for_status()
                    manifest = response.json()
                    break
                except (requests.RequestException, ValueError):
                    continue
            if not manifest:
                raise RuntimeError("官方源与镜像均无法获取模型信息，请检查网络或代理")
            revision = manifest["sha"]
            files = [f for f in manifest["siblings"] if any(fnmatch.fnmatch(f["rfilename"], pattern) for pattern in FILES)]
            required = {"config.json", "model.bin", "tokenizer.json"}
            if not required.issubset({f["rfilename"] for f in files}):
                raise RuntimeError("模型仓库缺少必要文件")
            for file in files:
                name = file["rfilename"]
                destination = folder / name
                expected = file.get("size") or file.get("lfs", {}).get("size")
                if destination.is_file() and expected and destination.stat().st_size == expected:
                    continue
                partial = destination.with_name(destination.name + ".incomplete")
                failures = 0
                while not expected or not partial.exists() or partial.stat().st_size < expected:
                    offset = partial.stat().st_size if partial.exists() else 0
                    base = sources[failures % len(sources)]
                    report(message="正在连接下载服务器" if not failures else f"连接中断，正在续传（重试 {failures}/6）",
                        download_source=base, download_file=name, downloaded_bytes=offset,
                        total_bytes=expected, percent=offset/expected*100 if expected else None)
                    try:
                        end = min(offset + 4 * 1024 * 1024, expected) - 1 if expected else offset + 4 * 1024 * 1024 - 1
                        headers = {"Range": f"bytes={offset}-{end}"}
                        with requests.get(base + "/" + target + "/resolve/" + revision + "/" + name,
                                headers=headers, stream=True, timeout=(5, 15)) as response:
                            response.raise_for_status()
                            if offset and (response.status_code != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-")):
                                raise RuntimeError("下载服务器未正确支持断点续传")
                            last = 0.0
                            with partial.open("ab" if offset else "wb") as out:
                                for chunk in response.iter_content(256 * 1024):
                                    if not chunk:
                                        continue
                                    out.write(chunk)
                                    offset += len(chunk)
                                    if time.monotonic() - last > 0.7:
                                        out.flush()
                                        report(message="正在下载模型文件", download_source=base, download_file=name,
                                            downloaded_bytes=offset, total_bytes=expected,
                                            percent=min(99.9,offset/expected*100) if expected else None)
                                        last = time.monotonic()
                        if offset != end + 1:
                            raise RuntimeError("下载分段长度与请求不一致")
                        failures = 0
                        if expected and offset >= expected:
                            break
                    except (requests.RequestException, RuntimeError) as exc:
                        failures += 1
                        if failures >= 6:
                            raise RuntimeError("下载连接连续失败，已保留断点，可重试续传或清理后重下") from exc
                        time.sleep(1)
                if expected and partial.stat().st_size != expected:
                    raise RuntimeError("下载文件大小不匹配，请清理后重试")
                checksum = file.get("lfs", {}).get("sha256")
                if checksum:
                    report(message="正在校验模型文件", download_file=name, percent=None)
                    digest = hashlib.sha256()
                    with partial.open("rb") as stream:
                        for block in iter(lambda: stream.read(1024 * 1024), b""):
                            digest.update(block)
                    if digest.hexdigest() != checksum:
                        raise RuntimeError("模型文件校验失败，请清理未完成下载后重试")
                partial.replace(destination)
            index.write_text(json.dumps({"repo": target, "revision": revision, "files": [{"name": f["rfilename"], "size": (folder / f["rfilename"]).stat().st_size} for f in files]}), encoding="utf-8")
            return str(folder)
        except Exception as exc:
            raise ModelDownloadError(model_size, str(exc)) from exc
