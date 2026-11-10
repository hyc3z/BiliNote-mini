import { spawn, execFile } from 'node:child_process'
import { mkdirSync, openSync, closeSync } from 'node:fs'
import path from 'node:path'
const projectRoot=__PROJECT_ROOT__
export async function apply(ctx){
  try {const response=await fetch('http://127.0.0.1:8483/api/sys_check',{signal:AbortSignal.timeout(1500)});if(response.ok)return}catch{}
  const backend=path.join(projectRoot,'backend');mkdirSync(path.join(backend,'logs'),{recursive:true})
  const out=openSync(path.join(backend,'logs','harness.stdout.log'),'a'),err=openSync(path.join(backend,'logs','harness.stderr.log'),'a')
  let process
  try{process=spawn(path.join(backend,'.venv','Scripts','python.exe'),['-u','main.py'],{cwd:backend,windowsHide:true,env:{...globalThis.process.env,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8',BACKEND_HOST:'127.0.0.1',BACKEND_PORT:'8483'},stdio:['ignore',out,err]})}finally{closeSync(out);closeSync(err)}
  process.on('error',error=>console.error('BiliNote backend startup failed:',error.message))
  ctx.effect(()=>()=>{if(process.exitCode===null&&process.pid){if(globalThis.process.platform==='win32')execFile('taskkill',['/PID',String(process.pid),'/T','/F'],{windowsHide:true},()=>{});else process.kill()}})
}
