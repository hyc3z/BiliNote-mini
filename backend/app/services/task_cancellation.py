import json,os,time,uuid
from pathlib import Path
from contextvars import ContextVar
from contextlib import contextmanager
current=ContextVar('cancel_task_id',default=None)
class TaskCancelled(Exception):pass

def marker(task_id):
 uuid.UUID(task_id)
 folder=Path(os.getenv('NOTE_OUTPUT_DIR','note_results'))/'.cancelled';folder.mkdir(parents=True,exist_ok=True)
 return folder/task_id

def cancelled(task_id):
 try:return bool(task_id and marker(task_id).exists())
 except (ValueError,TypeError,AttributeError):return False
def check(task_id=None):
 if cancelled(task_id or current.get()):raise TaskCancelled('任务已由用户停止，缓存已保留')
@contextmanager
def scope(task_id):
 token=current.set(task_id)
 try:check();yield
 finally:current.reset(token)
def clear(task_id):marker(task_id).unlink(missing_ok=True)
def finish(task_id):
 p=Path(os.getenv('NOTE_OUTPUT_DIR','note_results'))/f'{task_id}.status.json'
 try:data=json.loads(p.read_text(encoding='utf-8'))
 except (OSError,ValueError):data={}
 data.update(status='CANCELLED',message='已停止，缓存已保留',updated_at=time.time())
 temp=p.with_suffix('.cancel.tmp');temp.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');temp.replace(p)
def stop_all():
 from app.services.replay_chat import jobs_db
 folder=Path(os.getenv('NOTE_OUTPUT_DIR','note_results'));ids={};pending=0
 with jobs_db() as db:
  db.execute('BEGIN IMMEDIATE')
  for row in db.execute("SELECT task_id,state FROM jobs WHERE state IN ('PENDING','RUNNING')"):ids[row['task_id']]=row['state']
  for p in folder.glob('*.status.json'):
   try:
    record=json.loads(p.read_text(encoding='utf-8'));identifier=p.name.removesuffix('.status.json');uuid.UUID(identifier)
    if record.get('status') not in ('SUCCESS','FAILED','CANCELLED'):ids.setdefault(identifier,record.get('status'))
   except (OSError,ValueError):pass
  for identifier,state in ids.items():
   marker(identifier).touch()
   if state=='PENDING':finish(identifier);pending+=1
   else:
    p=folder/f'{identifier}.status.json'
    try:data=json.loads(p.read_text(encoding='utf-8'))
    except (OSError,ValueError):data={}
    data.update(status='CANCELLING',message='停止中：等待当前下载、转录片段或模型请求返回，不再执行后续步骤',updated_at=time.time());p.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
  db.execute("UPDATE jobs SET state='CANCELLED',error='用户停止' WHERE state IN ('PENDING','RUNNING')")
 return {'cancelled':pending,'stopping':len(ids)-pending,'task_ids':list(ids),'states':{identifier:('CANCELLED' if state=='PENDING' else 'CANCELLING') for identifier,state in ids.items()}}

