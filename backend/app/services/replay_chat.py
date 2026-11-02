"""On-demand discovery, durable jobs, and local result access. No scheduler."""
import html
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager

import requests
from app.services import library

UPLOADER = "2090606494"
ROOT = Path(__file__).resolve().parents[2]

def default_date():
    today = datetime.now(timezone(timedelta(hours=8))).date()
    return (today - timedelta(days=(today.weekday()-5)%7)).isoformat()

def title_date(title):
    found = re.search(r"(20[0-9]{2})[-/年]([0-9]{1,2})[-/月]([0-9]{1,2})", title)
    if not found:
        return None
    try:
        return datetime(*map(int,found.groups())).date().isoformat()
    except ValueError:
        return None

def api(route, params):
    from app.services.cookie_manager import CookieConfigManager
    headers = {"User-Agent":"Mozilla/5.0", "Referer":"https://www.bilibili.com"}
    cookie = CookieConfigManager().get("bilibili")
    if cookie:
        headers["Cookie"] = cookie
    response = requests.get("https://api.bilibili.com/"+route, params=params, headers=headers, timeout=(5,12))
    response.raise_for_status()
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError("B 站返回了非 JSON 响应，可能触发访问限制；可提供回放 BV 号") from exc
    if body.get("code") != 0:
        raise RuntimeError(f"B 站接口返回 {body.get('code')}，请检查 Cookie 或稍后重试")
    return body.get("data") or {}

def space_videos(page):
    params = {"mid":UPLOADER,"ps":30,"pn":page,"order":"pubdate"}
    try:
        return api("x/space/arc/search", params)
    except (requests.RequestException, RuntimeError):
        # WBI signing follows the algorithm shipped in yt-dlp's BiliBiliBaseIE.
        import hashlib
        from urllib.parse import urlencode
        headers={"User-Agent":"Mozilla/5.0","Referer":"https://www.bilibili.com"}
        response=requests.get('https://api.bilibili.com/x/web-interface/nav',headers=headers,timeout=(5,8))
        response.raise_for_status()
        info=response.json().get('data',{}).get('wbi_img',{})
        lookup=''.join(info.get(name,'').rsplit('/',1)[-1].split('.')[0] for name in ('img_url','sub_url'))
        if len(lookup)<64:
            raise RuntimeError("无法取得 B 站投稿接口的签名信息")
        indexes=[46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,29,28,14,39,12,38,41,13]
        key=''.join(lookup[i] for i in indexes)
        params['wts']=round(time.time())
        params={k:''.join(c for c in str(v) if c not in "!'()*") for k,v in sorted(params.items())}
        params['w_rid']=hashlib.md5((urlencode(params)+key).encode()).hexdigest()
        return api('x/space/wbi/arc/search',params)

def local_replays(day):
    rows = []
    for note in library.search():
        payload = library.get(note["task_id"])
        audio = payload.get("audio_meta", {})
        raw = audio.get("raw_info", {})
        if str(raw.get("uploader_id", "")) != UPLOADER:
            continue
        match = re.search(r"BV[0-9A-Za-z]+",note["source"])
        if match and "极客湾" in note["title"] and title_date(note["title"]) == day:
            rows.append({"bvid":match.group(),"title":note["title"],"source":note["source"],"from":"local","task_id":note["task_id"]})
    return rows

def discover(day=""):
    day = day or default_date()
    datetime.strptime(day,"%Y-%m-%d")
    rows = local_replays(day)
    known = {r["bvid"] for r in rows}
    online_ok = False
    warning = None
    try:
        for page in range(1,6):
            data = space_videos(page)
            videos = data.get("list",{}).get("vlist",[])
            if not videos and data.get("is_risk"):
                raise RuntimeError("B 站投稿列表触发访问限制")
            online_ok = True
            if not videos:
                break
            for video in videos:
                title = html.unescape(re.sub('<[^>]+>','',video.get("title", "")))
                if "极客湾" not in title or not any(word in title for word in ("回放","录播")) or title_date(title) != day:
                    continue
                bvid = video.get("bvid")
                if bvid and bvid not in known:
                    rows.append({"bvid":bvid,"title":title,"source":"https://www.bilibili.com/video/"+bvid,"from":"bilibili"})
                    known.add(bvid)
            oldest = min((v.get("created",0) for v in videos),default=0)
            if oldest and datetime.fromtimestamp(oldest,timezone(timedelta(hours=8))).date().isoformat() < day:
                break
            time.sleep(.4)
    except (requests.RequestException,RuntimeError,ValueError) as exc:
        warning = str(exc) if isinstance(exc,RuntimeError) else "B 站连接失败；本地结果仍可用"
    rows.sort(key=lambda r: (int(re.search(r"[pP](\d+)",r["title"]).group(1)) if re.search(r"[pP](\d+)",r["title"]) else 0,r["bvid"]))
    return {"replay_date":day,"uploader_id":UPLOADER,"replays":rows,"online_checked":online_ok,"completeness":"not_guaranteed","warning":warning,"suggested_web_search":f'site:bilibili.com/video "樱花云の录播姬" "极客湾" "{day}"' if warning else None,"note":"结果按标题中的直播日期归组；平台限制或后续补传可能导致缺失，不应宣称已覆盖整场直播。"}

def parts(bvid):
    if not re.fullmatch(r"BV[0-9A-Za-z]{10}",bvid):
        raise ValueError("需要有效的 BV 号")
    data = api("x/web-interface/view", {"bvid":bvid})
    pages = data.get("pages") or [{"cid":data["cid"],"page":1,"part":data.get("title", ""),"duration":data.get("duration",0)}]
    return [{"bvid":bvid,"cid":str(p["cid"]),"part":int(p.get("page",i+1)),"title":data.get("title","")+" · "+p.get("part", ""),"source":f"https://www.bilibili.com/video/{bvid}?p={int(p.get('page',i+1))}","duration":p.get("duration",0),"uploader_id":str(data.get("owner",{}).get("mid",""))} for i,p in enumerate(pages)]

@contextmanager
def jobs_db():
    folder = ROOT / "data"
    folder.mkdir(exist_ok=True)
    db = sqlite3.connect(os.getenv("MINI_CHAT_JOBS_DB", str(folder/"chat_jobs.sqlite3")),timeout=15)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS jobs(task_id TEXT PRIMARY KEY,bvid TEXT,cid TEXT,part INTEGER,title TEXT,source TEXT,provider_id TEXT,model_name TEXT,state TEXT,created_at REAL,error TEXT,UNIQUE(bvid,cid))")
        yield db
        db.commit()
    finally:
        db.close()

def find_saved(part):
    with library.database() as db:
        candidates = db.execute("SELECT task_id,payload FROM notes WHERE source LIKE ?",('%'+part['bvid']+'%',)).fetchall()
    for row in candidates:
        payload = json.loads(row["payload"])
        audio = payload.get("audio_meta",{})
        raw = audio.get("raw_info",{})
        if raw.get("cid") and str(raw["cid"]) == part["cid"]:
            return row["task_id"]
        video_id = audio.get("video_id","")
        matched = re.search(r"_p(\d+)$",video_id)
        if not raw.get("cid") and (int(matched.group(1)) if matched else 1) == part["part"]:
            return row["task_id"]
    return None

def default_model():
    from app.db.model_dao import get_all_models
    from app.services.provider import ProviderService
    models = get_all_models()
    selected = next((m for m in reversed(models) if (ProviderService.get_provider_by_id(m["provider_id"]) or {}).get("name")=="Mini 默认模型"),None)
    if not selected:
        raise RuntimeError("请先在网页设置中保存默认文字模型")
    return selected

def enqueue(bvids, start=True):
    all_parts = [part for bvid in dict.fromkeys(bvids) for part in parts(bvid)]
    if any(part.get("uploader_id",UPLOADER) != UPLOADER for part in all_parts):
        raise ValueError("回放不属于已指定的 UP 主，请先核对来源")
    return enqueue_parts(all_parts, start=start)


def enqueue_parts(all_parts, model=None, start=True):
    """Shared durable queue for explicitly selected web parts and chat replays."""
    all_parts = list({(p['bvid'], p['cid']): p for p in all_parts}.values())
    if not all_parts or len(all_parts)>60:
        raise ValueError("请选择 1–60 个视频分 P")
    selected = model
    result = []
    with jobs_db() as db:
        for part in all_parts:
            ready = find_saved(part)
            if ready:
                result.append({**part,"task_id":ready,"state":"SUCCESS","reused":True});continue
            selected = selected or default_model()
            existing = db.execute("SELECT * FROM jobs WHERE bvid=? AND cid=?",(part['bvid'],part['cid'])).fetchone()
            if existing and existing['state'] in ('PENDING','RUNNING'):
                result.append({**part,"task_id":existing['task_id'],"state":existing['state'],"reused":True});continue
            with library.database() as notes_db:
                removed = bool(existing and notes_db.execute('SELECT 1 FROM removed WHERE task_id=?',(existing['task_id'],)).fetchone())
            task_id = existing['task_id'] if existing and existing['state']=='FAILED' and not removed else str(uuid.uuid4())
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(bvid,cid) DO UPDATE SET task_id=excluded.task_id,state='PENDING',error=NULL,provider_id=excluded.provider_id,model_name=excluded.model_name",(task_id,part['bvid'],part['cid'],part['part'],part['title'],part['source'],selected['provider_id'],selected['model_name'],'PENDING',time.time(),None))
            folder = Path(os.getenv('NOTE_OUTPUT_DIR','note_results'));folder.mkdir(exist_ok=True)
            (folder/f'{task_id}.status.json').write_text(json.dumps({'status':'PENDING','started_at':time.time(),'title':part['title']}),encoding='utf-8')
            result.append({**part,"task_id":task_id,"state":"PENDING","reused":False})
    if start and any(row['state']!='SUCCESS' for row in result):
        start_worker()
    return {"parts":result,"note":"PENDING/RUNNING 仅表示已入队或处理中，不能当作已完成。"}

def start_worker():
    logs = ROOT / 'logs';logs.mkdir(exist_ok=True)
    with (logs/'chat-worker.log').open('ab') as out:
        subprocess.Popen([sys.executable,'-u',str(ROOT/'chat_worker.py')],cwd=str(ROOT),stdin=subprocess.DEVNULL,stdout=out,stderr=out,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),close_fds=True)

def job_status(task_ids):
    result=[]
    for identifier in task_ids:
        uuid.UUID(identifier)
        with jobs_db() as db:
            row=db.execute('SELECT * FROM jobs WHERE task_id=?',(identifier,)).fetchone()
        cached=library.get(identifier)
        file=Path(os.getenv('NOTE_OUTPUT_DIR','note_results'))/f'{identifier}.status.json'
        try:progress=json.loads(file.read_text(encoding='utf-8'))
        except (OSError,ValueError):progress={}
        result.append({'task_id':identifier,'state':'SUCCESS' if cached else ('FAILED' if row and row['state']=='FAILED' else progress.get('status',row['state'] if row else 'UNKNOWN')),'progress':progress,'source':row['source'] if row else None,'transcript_ready':(file.parent/f'{identifier}_transcript.json').exists()})
    return result
