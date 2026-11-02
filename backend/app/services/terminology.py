import json
import os
from pathlib import Path
import re
import uuid
from app.services import library

DEFAULT_TERMS=['骁龙8E5','骁龙8EE6','高通','天玑','麒麟','玄戒','锐龙','酷睿','RTX 5070','DLSS']

def terms():
    try:return json.loads(Path('config/terminology.json').read_text(encoding='utf-8'))['terms']
    except (OSError,ValueError,KeyError):return DEFAULT_TERMS

def save_terms(items):
    items=list(dict.fromkeys(word.strip() for word in items if word.strip()))
    if len('、'.join(items))>200:raise ValueError('词表合计最多 200 字符，避免提示过长')
    folder=Path('config');folder.mkdir(exist_ok=True)
    (folder/'terminology.json').write_text(json.dumps({'terms':items},ensure_ascii=False),encoding='utf-8')

def load(task_id):
    uuid.UUID(task_id)
    folder=Path(os.getenv('NOTE_OUTPUT_DIR','note_results'))
    file=folder/f'{task_id}_transcript.json'
    if file.is_file():return file,json.loads(file.read_text(encoding='utf-8'))
    note=library.get(task_id)
    if not note:raise ValueError('找不到逐字稿')
    return file,note['transcript']

def correct(task_id,old,new,apply=False):
    if not old.strip() or not new.strip() or len(old)>100 or len(new)>100:raise ValueError('请填写 1–100 字符的原词和替换词')
    file,data=load(task_id)
    # Numeric/alphanumeric boundaries prevent replacing 815 inside 1815 or 8150.
    pattern=re.compile(r'(?<![0-9A-Za-z])'+re.escape(old)+r'(?![0-9A-Za-z])',re.I)
    changes=[]
    corrected=json.loads(json.dumps(data))
    for segment in corrected['segments']:
        before=segment['text'];after=pattern.sub(lambda _:new,before)
        if before!=after:
            changes.append({'start':segment['start'],'before':before,'after':after})
            segment['text']=after
    if apply and changes:
        original=file.with_name(task_id+'_transcript.original.json')
        if not original.exists():original.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        corrected['full_text']=' '.join(item['text'] for item in corrected['segments'])
        raw=corrected.get('raw') or {}
        raw.setdefault('corrections',[]).append({'from':old,'to':new,'changes':changes})
        corrected['raw']=raw
        temp=file.with_suffix('.tmp');temp.write_text(json.dumps(corrected,ensure_ascii=False),encoding='utf-8');temp.replace(file)
        text='\n'.join(f"[{int(s['start'])//60:02d}:{int(s['start'])%60:02d}] {s['text']}" for s in corrected['segments'])
        file.with_suffix('.txt').write_text(text,encoding='utf-8')
        note=library.get(task_id)
        if note:
            note['transcript']=corrected
            note['summary_stale']=True
            library.save(task_id,note)
            result=file.parent/f'{task_id}.json'
            result.write_text(json.dumps(note,ensure_ascii=False),encoding='utf-8')
    return {'matches':len(changes),'examples':changes[:5],'transcript':corrected if apply else None,'summary_stale':bool(apply and changes)}

# Tag dictionaries are opt-in per BV; untagged videos receive no domain hints.
from contextvars import ContextVar
from functools import wraps
from filelock import FileLock
active_source = ContextVar('terminology_source', default='')

def tag_config():
    try:
        return json.loads(Path('config/tag_terms.json').read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {'tags':{'数码':terms()},'videos':{}}

def update_tag_config(tag=None, items=None, bvid=None, tags=None):
    folder=Path('config');folder.mkdir(exist_ok=True)
    with FileLock(str(folder/'tag_terms.lock')):
        data=tag_config()
        if tag is not None:
            tag=tag.strip()
            if not tag or len(tag)>30:raise ValueError('标签名称须为 1–30 字符')
            clean=list(dict.fromkeys(w.strip() for w in items if w.strip()))
            if len('、'.join(clean))>200:raise ValueError('每个标签词表最多 200 字符')
            data['tags'][tag]=clean
        if bvid is not None:
            if not re.fullmatch(r'BV[0-9A-Za-z]{10}',bvid):raise ValueError('无效 BV 号')
            if any(t not in data['tags'] for t in tags):raise ValueError('标签不存在')
            data['videos'][bvid]=list(dict.fromkeys(tags))
        target=folder/'tag_terms.json';temp=target.with_suffix('.tmp')
        temp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');temp.replace(target)
    return data

def scoped_terms():
    match=re.search(r'BV[0-9A-Za-z]{10}',active_source.get())
    if not match:return []
    data=tag_config()
    return list(dict.fromkeys(w for tag in data['videos'].get(match[0],[]) for w in data['tags'].get(tag,[])))

def with_video_terms(fn):
    @wraps(fn)
    def scoped(self,*args,**kwargs):
        token=active_source.set(str(kwargs.get('video_url',args[0] if args else '')))
        try:return fn(self,*args,**kwargs)
        finally:active_source.reset(token)
    return scoped
