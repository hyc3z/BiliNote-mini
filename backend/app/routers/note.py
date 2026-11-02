# app/routers/note.py
import json
import os
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel, validator, field_validator, model_validator
from dataclasses import asdict

from app.db.video_task_dao import get_task_by_video
from app.enmus.exception import NoteErrorEnum
from app.enmus.note_enums import DownloadQuality
from app.exceptions.note import NoteError
from app.services.note import NoteGenerator, logger
from app.services.task_serial_executor import task_serial_executor
from app.utils.response import ResponseWrapper as R
from app.utils.url_parser import extract_video_id, normalize_video_url
from app.validators.video_url_validator import is_supported_video_url
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
import httpx
from app.enmus.task_status_enums import TaskStatus

# from app.services.downloader import download_raw_audio
# from app.services.whisperer import transcribe_audio

router = APIRouter()


class RecordRequest(BaseModel):
    video_id: str
    platform: str


class VideoRequest(BaseModel):
    video_url: str
    platform: str
    quality: DownloadQuality
    screenshot: Optional[bool] = False
    link: Optional[bool] = False
    model_name: str
    provider_id: str
    task_id: Optional[str] = None
    format: Optional[list] = []
    style: str = None
    extras: Optional[str]=None
    video_understanding: Optional[bool] = False
    video_interval: Optional[int] = 0
    grid_size: Optional[list] = []
    # 客户端（如浏览器插件）已经在用户浏览器里抓到字幕，直接传给后端复用，
    # 跳过 download_subtitles 和音频转写。形如：
    #   {"language": "zh", "full_text": "...", "segments": [{"start","end","text"}, ...]}
    prefetched_transcript: Optional[dict] = None

    @model_validator(mode="before")
    @classmethod
    def normalize_url(cls, data):
        # 稍后再看/收藏夹/带追踪参数的 B 站链接先规范化成标准 /video/BVxxx 形式，
        # 后续校验和 yt-dlp 下载拿到的都是干净链接
        if isinstance(data, dict) and data.get("platform") == "bilibili" and data.get("video_url"):
            data["video_url"] = normalize_video_url(str(data["video_url"]))
        if isinstance(data, dict):
            if data.get("platform") != "bilibili":
                raise ValueError("精简版仅支持 B 站视频")
            data.update(screenshot=False, video_understanding=False, grid_size=[],
                        format=["link"], link=True, style="minimal")
        return data

    @field_validator("video_url")
    def validate_supported_url(cls, v):
        url = str(v)
        parsed = urlparse(url)
        if parsed.scheme in ("http", "https"):
            # 是网络链接，继续用原有平台校验
            if not is_supported_video_url(url):
                raise NoteError(code=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.code,
                                message=NoteErrorEnum.PLATFORM_NOT_SUPPORTED.message)

        return v


NOTE_OUTPUT_DIR = os.getenv("NOTE_OUTPUT_DIR", "note_results")
UPLOAD_DIR = "uploads"


def save_note_to_file(task_id: str, note):
    os.makedirs(NOTE_OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json"), "w", encoding="utf-8") as f:
        json.dump(asdict(note), f, ensure_ascii=False, indent=2)
    from app.services.library import save
    save(task_id, asdict(note))


def _persist_prefetched_transcript(task_id: str, transcript: dict) -> None:
    """把客户端预取的字幕写到 NoteGenerator 期望的转写缓存文件里。

    NoteGenerator.generate 会优先读 <task_id>_transcript.json，命中即跳过 download_subtitles
    与音频转写流程。要求字段：language(可空)/full_text/segments[{start,end,text}]
    """
    segments = transcript.get("segments") or []
    cleaned_segments = []
    for s in segments:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        cleaned_segments.append({
            "start": float(s.get("start", 0)),
            "end": float(s.get("end", 0)),
            "text": text,
        })
    if not cleaned_segments:
        raise ValueError("prefetched_transcript 没有可用的 segments")

    full_text = transcript.get("full_text") or " ".join(s["text"] for s in cleaned_segments)
    payload = {
        "language": transcript.get("language") or "zh",
        "full_text": full_text,
        "segments": cleaned_segments,
    }

    os.makedirs(NOTE_OUTPUT_DIR, exist_ok=True)
    target = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}_transcript.json")
    with open(target, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"已写入客户端预取字幕缓存: {target} ({len(cleaned_segments)} 段)")


def run_note_task(task_id: str, video_url: str, platform: str, quality: DownloadQuality,
                  link: bool = False, screenshot: bool = False, model_name: str = None, provider_id: str = None,
                  _format: list = None, style: str = None, extras: str = None, video_understanding: bool = False,
                  video_interval=0, grid_size=[]
                  ):

    if not model_name or not provider_id:
        raise HTTPException(status_code=400, detail="请选择模型和提供者")

    def _execute_note_task():
        return NoteGenerator().generate(
            video_url=video_url,
            platform=platform,
            quality=quality,
            task_id=task_id,
            model_name=model_name,
            provider_id=provider_id,
            link=link,
            _format=_format,
            style=style,
            extras=extras,
            screenshot=screenshot,
            video_understanding=video_understanding,
            video_interval=video_interval,
            grid_size=grid_size,
        )

    logger.info(f"任务进入执行队列 (task_id={task_id})")
    note = task_serial_executor.run(_execute_note_task)
    logger.info(f"Note generated: {task_id}")
    if not note or not note.markdown:
        logger.warning(f"任务 {task_id} 执行失败，跳过保存")
        return
    save_note_to_file(task_id, note)



@router.post('/delete_task')
def delete_task(data: RecordRequest):
    try:
        # TODO: 待持久化完成
        # NoteGenerator().delete_note(video_id=data.video_id, platform=data.platform)
        return R.success(msg='删除成功')
    except Exception as e:
        return R.error(msg=e)


@router.post("/generate_note")
def generate_note(data: VideoRequest, background_tasks: BackgroundTasks):
    try:
        if data.task_id:
            uuid.UUID(data.task_id)
        video_id = extract_video_id(data.video_url, data.platform)
        # if not video_id:
        #     raise HTTPException(status_code=400, detail="无法提取视频 ID")
        # existing = get_task_by_video(video_id, data.platform)
        # if existing:
        #     return R.error(
        #         msg='笔记已生成，请勿重复发起',
        #
        #     )
        if data.task_id:
            # 如果传了task_id，说明是重试！
            task_id = data.task_id
            logger.info(f"重试模式，复用已有 task_id={task_id}")
        else:
            # 正常新建任务
            task_id = str(uuid.uuid4())

        # 统一先写入 PENDING，表示已进入队列等待串行执行
        NoteGenerator()._update_status(task_id, TaskStatus.PENDING)

        # 客户端已经抓好字幕的话，写到转写缓存文件，NoteGenerator 的 cache-hit 逻辑会直接用上
        if data.prefetched_transcript:
            try:
                _persist_prefetched_transcript(task_id, data.prefetched_transcript)
            except Exception as e:
                logger.warning(f"写入预取字幕失败 (task_id={task_id}): {e}")

        background_tasks.add_task(run_note_task, task_id, data.video_url, data.platform, data.quality, data.link,
                                  data.screenshot, data.model_name, data.provider_id, data.format, data.style,
                                  data.extras, data.video_understanding, data.video_interval, data.grid_size)
        return R.success({"task_id": task_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/task_status/{task_id}")
def get_task_status(task_id: str, include_transcript: bool = True):
    try:
        uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效任务编号")
    status_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.status.json")
    result_path = os.path.join(NOTE_OUTPUT_DIR, f"{task_id}.json")

    partial_result = {}
    if include_transcript:
        for suffix, key in (("_transcript.json", "transcript"), ("_audio.json", "audio_meta")):
            cached_path = Path(NOTE_OUTPUT_DIR) / f"{task_id}{suffix}"
            try:
                payload = json.loads(cached_path.read_text(encoding="utf-8"))
                if key != "transcript" or payload.get("segments"):
                    partial_result[key] = payload
            except (OSError, ValueError):
                pass

    # 优先读状态文件
    if os.path.exists(status_path):
        with open(status_path, "r", encoding="utf-8") as f:
            status_content = json.load(f)

        import time
        now = time.time()
        progress = dict(status_content)
        end = progress.get("updated_at", now) if progress.get("status") in ("SUCCESS", "FAILED") else now
        progress["elapsed_seconds"] = max(0, end - progress.get("started_at", end))
        progress["stage_elapsed_seconds"] = max(0, end - progress.get("stage_started_at", end))
        status = status_content.get("status")
        message = status_content.get("message", "")

        if status == TaskStatus.SUCCESS.value:
            # 成功状态的话，继续读取最终笔记内容
            if os.path.exists(result_path):
                with open(result_path, "r", encoding="utf-8") as rf:
                    result_content = json.load(rf)
                return R.success({
                    "status": status,
                    "result": result_content,
                    "message": message,
                    "progress": progress,
                    "task_id": task_id
                })
            else:
                # 理论上不会出现，保险处理
                return R.success({
                    "status": TaskStatus.PENDING.value,
                    "message": "任务完成，但结果文件未找到",
                    "task_id": task_id
                })

        if status == TaskStatus.FAILED.value:
            return R.success({"status": TaskStatus.FAILED.value, "message": message or "任务失败", "progress": progress, "partial_result": partial_result, "task_id": task_id})

        # 处理中状态
        return R.success({
            "status": status,
            "message": message,
                    "progress": progress,
            "partial_result": partial_result,
            "task_id": task_id
        })

    # 没有状态文件，但有结果
    if os.path.exists(result_path):
        with open(result_path, "r", encoding="utf-8") as f:
            result_content = json.load(f)
        return R.success({
            "status": TaskStatus.SUCCESS.value,
            "result": result_content,
            "task_id": task_id
        })

    # 什么都没有，默认PENDING
    return R.success({
        "status": TaskStatus.PENDING.value,
        "message": "任务排队中",
        "task_id": task_id
    })


class ClearModelDownloadRequest(BaseModel):
    task_id: str

@router.post("/clear_failed_model_download")
def clear_failed_model_download(data: ClearModelDownloadRequest):
    try:
        uuid.UUID(data.task_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效任务编号")
    target = Path(NOTE_OUTPUT_DIR) / f"{data.task_id}.status.json"
    if not target.is_file():
        raise HTTPException(status_code=404, detail="任务不存在")
    record = json.loads(target.read_text(encoding="utf-8"))
    if record.get("status") != "FAILED" or not record.get("can_reset_model_download"):
        raise HTTPException(status_code=409, detail="仅下载失败的任务可以清理")
    from app.transcriber.whisper_models import resolve_whisper_model, is_local_target
    from app.transcriber.model_transfer import clean_incomplete
    from app.utils.path_helper import get_model_dir
    repo = resolve_whisper_model(record["model"])
    if is_local_target(repo):
        raise HTTPException(status_code=409, detail="不清理用户提供的本地模型")
    try:
        count = clean_incomplete(get_model_dir("whisper"), repo)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return R.success(data={"removed_files": count})


@router.get("/library")
def search_library(q: str = ""):
    from app.services.library import search
    return R.success(data=search(q[:500]))

@router.get("/library/{task_id}")
def library_result(task_id: str):
    from app.services.library import get
    result = get(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return R.success(data=result)

@router.delete("/tasks/{task_id}")
def remove_history_task(task_id: str):
    try:
        uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="无效任务编号")
    folder = Path(NOTE_OUTPUT_DIR).resolve()
    status_file = folder / f"{task_id}.status.json"
    if status_file.exists():
        record = json.loads(status_file.read_text(encoding="utf-8"))
        if record.get("status") not in ("SUCCESS", "FAILED"):
            raise HTTPException(status_code=409, detail="处理中任务不能删除，请等待处理结束")
    from app.services.replay_chat import jobs_db
    with jobs_db() as db:
        job=db.execute('SELECT state FROM jobs WHERE task_id=?',(task_id,)).fetchone()
        if job and job['state'] in ('PENDING','RUNNING'):
            raise HTTPException(status_code=409, detail="聊天后台任务仍在处理中，不能删除")
        db.execute("UPDATE jobs SET state='DELETED' WHERE task_id=?",(task_id,))
    from app.services.library import delete
    delete(task_id)
    for suffix in (".json", ".status.json", "_audio.json", "_transcript.json", "_transcript.txt", "_markdown.md", "_markdown.gpt.checkpoint.json"):
        target = folder / (task_id + suffix)
        if target.is_file() and not target.is_symlink():
            target.unlink()
    return R.success()


@router.get("/chat_jobs")
def chat_jobs():
    from app.services.replay_chat import jobs_db
    with jobs_db() as db:
        rows=db.execute("SELECT task_id,title,source,state,created_at FROM jobs WHERE state != 'DELETED' ORDER BY created_at DESC LIMIT 100").fetchall()
    return R.success(data=[dict(row) for row in rows])

class CorrectionRequest(BaseModel):
    old:str
    new:str
    apply:bool=False

@router.post('/tasks/{task_id}/correction')
def correct_terminology(task_id:str,data:CorrectionRequest):
    status=Path(NOTE_OUTPUT_DIR)/f'{task_id}.status.json'
    try:
        uuid.UUID(task_id)
        if status.is_file() and json.loads(status.read_text(encoding='utf-8')).get('status') not in ('SUCCESS','FAILED'):
            raise HTTPException(409,'请等待当前任务完成后校正')
        from app.services.terminology import correct
        return R.success(data=correct(task_id,data.old,data.new,data.apply))
    except ValueError as exc:raise HTTPException(422,str(exc))


class SelectionRequest(BaseModel):
    video_url: str

class BatchRequest(SelectionRequest):
    keys: list[str]
    provider_id: str
    model_name: str

@router.post('/video_selection')
def video_selection(data: SelectionRequest):
    try:
        from app.services.video_selection import inspect
        return R.success(data=inspect(data.video_url))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        raise HTTPException(502, str(exc))

@router.post('/prepare_selection')
def prepare_selection(data: BatchRequest):
    try:
        from app.db.model_dao import get_all_models
        selected=next((m for m in get_all_models() if str(m['provider_id'])==data.provider_id and m['model_name']==data.model_name), None)
        if not selected:
            raise ValueError('请选择已启用的总结模型')
        from app.services.video_selection import prepare
        return R.success(data=prepare(data.video_url, data.keys, selected))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:
        raise HTTPException(502, str(exc))
