"""Durable submission membership without changing worker job schema."""
import json,time,uuid
from app.services.replay_chat import jobs_db

def schema(db):
 db.execute('CREATE TABLE IF NOT EXISTS submission_batches(id TEXT PRIMARY KEY,title TEXT,created REAL,inferred INTEGER)')
 db.execute('CREATE TABLE IF NOT EXISTS submission_members(batch_id TEXT,task_id TEXT,PRIMARY KEY(batch_id,task_id))')

def record(title,parts):
 identifier=str(uuid.uuid4())
 with jobs_db() as db:
  schema(db)
  db.execute('INSERT INTO submission_batches VALUES(?,?,?,0)',(identifier,title,time.time()))
  db.executemany('INSERT OR IGNORE INTO submission_members VALUES(?,?)',[(identifier,p['task_id']) for p in parts])
 return identifier

def list_batches():
 with jobs_db() as db:
  schema(db)
  # Old releases had no submission ID: label the timestamp-based reconstruction explicitly.
  rows=db.execute("SELECT task_id,created_at FROM jobs WHERE state!='DELETED' AND task_id NOT IN (SELECT task_id FROM submission_members) ORDER BY created_at,task_id").fetchall()
  groups=[]
  for row in rows:
   if not groups or row['created_at']-groups[-1][-1]['created_at']>60:groups.append([])
   groups[-1].append(dict(row))
  for group in groups:
   identifier=str(uuid.uuid5(uuid.NAMESPACE_URL,'bilinote-history:'+group[0]['task_id']))
   db.execute('INSERT OR IGNORE INTO submission_batches VALUES(?,?,?,1)',(identifier,'历史导入 · '+time.strftime('%m/%d %H:%M',time.localtime(group[0]['created_at'])),group[0]['created_at']))
   db.executemany('INSERT OR IGNORE INTO submission_members VALUES(?,?)',[(identifier,p['task_id']) for p in group])
  result=[]
  for batch in db.execute('SELECT * FROM submission_batches ORDER BY created DESC').fetchall():
   ids=[row[0] for row in db.execute("SELECT m.task_id FROM submission_members m LEFT JOIN jobs j ON m.task_id=j.task_id WHERE m.batch_id=? AND COALESCE(j.state,'')!='DELETED'",(batch['id'],))]
   if ids:result.append({'id':batch['id'],'title':batch['title'],'created_at':batch['created'],'inferred':bool(batch['inferred']),'task_ids':ids})
 return result
