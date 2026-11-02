import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { useTaskStore } from '@/store/taskStore'
import { useModelStore } from '@/store/modelStore'
import { generateNote } from '@/services/note'
import request from '@/utils/request'
import { ArrowUpRight, Plus, Settings2, AudioLines, FileText, Download, RotateCcw, Check, CircleAlert, Loader2, Link2, Clock3, Cpu, Search, MoreHorizontal, Trash2, BookOpen, Sparkles } from 'lucide-react'
import './mini.css'
import CorrectionDialog from '@/pages/CorrectionDialog'


const labels: Record<string, string> = { MODEL_DOWNLOADING: '下载模型', MODEL_LOADING: '加载模型', PENDING: '排队中', PARSING: '读取字幕', DOWNLOADING: '读取媒体', TRANSCRIBING: '音频转录', SUMMARIZING: '总结观点', SAVING: '保存中', SUCCESS: '已完成', FAILED: '失败' }
const time = (s: number) => [Math.floor(s / 3600), Math.floor(s / 60) % 60, Math.floor(s) % 60].map(n => String(n).padStart(2, '0')).join(':')
function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
  const a = document.createElement('a'); a.href = url; a.download = name; a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
export function HomePage() {
  const store = useTaskStore()
  const { modelList, loadEnabledModels } = useModelStore()
  const [url, setUrl] = useState('')
  const [model, setModel] = useState(localStorage.getItem('mini-model') || '')
  const [tab, setTab] = useState('summary')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [correcting,setCorrecting]=useState(false)
  const [library, setLibrary] = useState<any[]>([])
  const [menu, setMenu] = useState<{id:string,x:number,y:number}|null>(null)
  const [searchError, setSearchError] = useState('')
  useEffect(() => {
    const close = () => setMenu(null)
    const key = (event: KeyboardEvent) => { if(event.key === 'Escape') close() }
    window.addEventListener('click', close); window.addEventListener('keydown', key); window.addEventListener('resize', close)
    return () => { window.removeEventListener('click', close); window.removeEventListener('keydown', key); window.removeEventListener('resize', close) }
  }, [])
  useEffect(() => {
    let cancelled = false
    const timer = setTimeout(() => { request.get('/library', {params:{q:query}}).then((rows:any) => {if(!cancelled){setLibrary(rows);setSearchError('')}}).catch(() => {if(!cancelled)setSearchError('本地资料库暂时无法连接')}) }, 200)
    return () => { cancelled=true; clearTimeout(timer) }
  }, [query, store.tasks.filter(t => t.status === 'SUCCESS').length])
  async function openSaved(row:any) {
    try {
      const result:any = await request.get('/library/'+row.task_id)
      if(!store.tasks.some(t=>t.id===row.task_id)) store.addPendingTask(row.task_id,'bilibili',{video_url:row.source,platform:'bilibili',quality:'medium',model_name:'',provider_id:''} as any)
      store.updateTaskContent(row.task_id,{status:'SUCCESS',markdown:result.markdown,transcript:result.transcript,audioMeta:result.audio_meta,summaryStale:!!result.summary_stale})
      store.setCurrentTask(row.task_id);setTab('summary');setError('')
    } catch(e:any) {setError(e?.msg || e?.detail || '读取笔记失败')}
  }
  function openMenu(event:React.MouseEvent,id:string) {
    event.preventDefault();event.stopPropagation()
    setMenu({id,x:Math.max(8,Math.min(event.clientX,window.innerWidth-225)),y:Math.max(8,Math.min(event.clientY,window.innerHeight-125))})
  }
  async function deleteTask(id:string) {
    setMenu(null)
    try { await request.delete('/tasks/'+id); await store.removeTask(id); setLibrary(rows=>rows.filter(r=>r.task_id!==id)) }
    catch(e:any) {setError(e?.msg || e?.detail || '删除失败')}
  }
  useEffect(() => { loadEnabledModels() }, [])
  useEffect(() => {
    let stopped = false
    async function syncChatJobs() {
      try {
        const jobs:any = await request.get('/chat_jobs', {suppressToast:true})
        if(stopped) return
        const current = useTaskStore.getState()
        for(const job of jobs) {
          if(current.tasks.some(t=>t.id===job.task_id)) continue
          const selectedId = useTaskStore.getState().currentTaskId
          current.addPendingTask(job.task_id,'bilibili',{video_url:job.source,platform:'bilibili',quality:'medium',model_name:'',provider_id:''} as any)
          if(selectedId) current.setCurrentTask(selectedId)
        }
      } catch { /* Web server may not yet have the optional chat adapter. */ }
    }
    syncChatJobs()
    const timer=setInterval(syncChatJobs,5000)
    return()=>{stopped=true;clearInterval(timer)}
  }, [])
  const task = store.tasks.find(t => t.id === store.currentTaskId)
  const markdown = typeof task?.markdown === 'string' ? task.markdown : task?.markdown?.[0]?.content || ''
  const active = task && !['SUCCESS', 'FAILED'].includes(task.status)
  const selected = modelList.find(m => String(m.id) === String(model)) || modelList[0]
  async function submit(retry = false) {
    setError('')
    if (!selected) { setError('请先在设置中配置并启用一个文字模型。'); return }
    if (retry && !task) return
    const input = (retry ? task!.formData.video_url : url).trim()
    if (!input) { setError('请输入 B 站链接或 BV 号。'); return }
    setBusy(true)
    const payload = { video_url: input, platform: 'bilibili', quality: 'medium', model_name: selected.model_name, provider_id: selected.provider_id, format: ['link'], link: true, style: 'minimal', grid_size: [] }
    try {
      const result: any = await generateNote({ ...payload, ...(retry ? { task_id: task!.id } : {}) })
      if (retry) store.updateTaskContent(task!.id, { status: 'PENDING', formData: payload, message: '' } as any)
      else store.addPendingTask(result.task_id, 'bilibili', payload)
    } catch (e: any) { setError(e?.msg || '提交失败，请检查后端连接。') }
    finally { setBusy(false) }
  }
  async function clearAndRetry() {
    if (!task) return
    setBusy(true); setError('')
    try { await request.post('/clear_failed_model_download', { task_id: task.id }) }
    catch (e: any) { setError(e?.msg || e?.detail || '清理失败'); setBusy(false); return }
    setBusy(false)
    await submit(true)
  }
  const progress = task?.progress
  const transcript = task?.transcript?.segments || []
  const transcriptText = transcript.map(s => '[' + time(s.start) + '] ' + s.text).join('\n')
  const stages = ['读取字幕', '准备音轨', '下载模型', '加载模型', '音频转录', '总结观点']
  const stageIndex = ({ PARSING: 0, DOWNLOADING: 1, MODEL_DOWNLOADING: 2, MODEL_LOADING: 3, TRANSCRIBING: 4, SUMMARIZING: 5, SAVING: 5, SUCCESS: 6 } as Record<string, number>)[task?.status || ''] ?? -1
  const title = task?.audioMeta?.title || '回放整理'
  const shortTitle = (t: typeof task) => t?.audioMeta?.title || t?.formData.video_url.match(/BV[0-9A-Za-z]+/)?.[0] || 'B 站回放'
  return <div className="mini-app">
    <aside className="mini-sidebar">
      <Link className="mini-brand" to="/"><span className="mini-logo"><AudioLines size={21} /></span><span>BiliNote <em>mini</em></span></Link>
      <button className="mini-new" onClick={() => { store.setCurrentTask(null); setUrl(''); setError('') }}><Plus size={17}/> 新建整理</button>
      <label className="mini-search"><Search size={15}/><input aria-label="搜索本地笔记" placeholder="搜索标题、观点、逐字稿" value={query} onChange={event=>setQuery(event.target.value)}/><kbd>⌕</kbd></label>
      <div className="mini-side-label">{query ? '检索结果' : '最近整理'} <span>{query ? library.length : store.tasks.length}</span></div>
      <nav className="mini-history">
        {!query && store.tasks.map(t=><div key={t.id} className={'mini-task-wrap '+(t.id===task?.id?'selected':'')} onContextMenu={event=>openMenu(event,t.id)}><button className={'mini-task '+(t.id===task?.id?'selected':'')} onClick={()=>{store.setCurrentTask(t.id);setTab('summary');setError('')}}><FileText size={16}/><span><strong title={shortTitle(t)}>{shortTitle(t)}</strong><small><i className={t.status==='FAILED'?'failed':t.status==='SUCCESS'?'done':'working'}/>{labels[t.status]||t.status} · {new Date(t.createdAt).toLocaleDateString('zh-CN',{month:'numeric',day:'numeric'})}</small></span></button><button className="mini-task-more" aria-label={'更多操作 '+shortTitle(t)} onClick={event=>openMenu(event,t.id)}><MoreHorizontal size={16}/></button></div>)}
        <div className="mini-side-label mini-library-label"><BookOpen size={12}/>{query ? '已搜索本地全文' : '已保存的笔记'}<span>{library.length}</span></div>
        {searchError && <p className="mini-side-empty">{searchError}</p>}
        {library.filter(row=>query || !store.tasks.some(t=>t.id===row.task_id)).map(row=><div key={row.task_id} className="mini-task-wrap" onContextMenu={event=>openMenu(event,row.task_id)}><button className="mini-task" onClick={()=>openSaved(row)}><BookOpen size={16}/><span><strong title={row.title}>{row.title}</strong><small><i className="done"/>保存在本机</small></span></button><button className="mini-task-more" aria-label={'更多操作 '+row.title} onClick={event=>openMenu(event,row.task_id)}><MoreHorizontal size={16}/></button></div>)}
        {query && !library.length && !searchError && <p className="mini-side-empty">没有找到相关笔记。可以换一个型号或关键词。</p>}
        {!query && !store.tasks.length && !library.length && <p className="mini-side-empty">粘贴第一条链接，建立你的观点资料库。</p>}
      </nav>
      <Link className="mini-settings" to="/settings"><Settings2 size={17}/> 模型与设置 <ArrowUpRight size={15}/></Link>
      <p className="mini-local"><span/> 本地转录 · 自己掌握内容</p>
    </aside>
    {correcting && task && <CorrectionDialog taskId={task.id} onClose={()=>setCorrecting(false)} onApply={transcript=>{store.updateTaskContent(task.id,{transcript,summaryStale:true});}}/>}
    {menu && <div className="mini-context" role="menu" aria-label="任务操作" style={{left:menu.x,top:menu.y}} onClick={event=>event.stopPropagation()}><p>任务操作</p><button role="menuitem" disabled={store.tasks.some(t=>t.id===menu.id && !['FAILED','SUCCESS'].includes(t.status))} onClick={()=>deleteTask(menu.id)}><Trash2 size={15}/>删除这条记录</button><small>移除笔记与任务文件，保留共享缓存</small></div>}
    <main className="mini-main">
      <header className="mini-topbar"><span>工作台 <span className="mini-slash">/</span> 回放笔记</span><span className="mini-model-pill"><span/>{selected?.model_name || '尚未配置模型'}</span></header>
      <div className="mini-content">
        <div className="mini-heading"><div><p className="mini-eyebrow">LESS WATCHING, MORE UNDERSTANDING</p><h1>长回放，<br className="mini-editorial-break"/><span>留下有用的观点。</span></h1><p>从 B 站链接到可回看的笔记，保留依据、限定条件和时间戳。</p></div><span className="mini-heading-icon"><Sparkles size={34}/><i>MAKE IT<br/>WORTH KEEPING.</i></span></div>
        <form className="mini-input-card" onSubmit={e => { e.preventDefault(); submit() }}><div className="mini-link-input"><Link2 size={19}/><input aria-label="B站链接或BV号" placeholder="粘贴 B 站视频链接或 BV 号" value={url} onChange={e => setUrl(e.target.value)}/><button className="mini-primary" disabled={busy}>{busy ? <Loader2 size={16} className="mini-spin"/> : <Plus size={16}/>}开始整理</button></div><div className="mini-input-footer"><span>字幕优先 · 无字幕时本地转录</span><label>总结模型 <select aria-label="总结模型" value={selected?.id || ''} onChange={e => {setModel(e.target.value); localStorage.setItem('mini-model',e.target.value)}}><option value="" disabled>前往设置添加模型</option>{modelList.map(m => <option key={m.id} value={m.id}>{m.model_name}</option>)}</select></label></div></form>
        {error && <div role="alert" className="mini-error"><CircleAlert size={17}/>{error}</div>}
        {!task ? <section className="mini-empty"><div className="mini-empty-symbol"><FileText size={30}/></div><h2>把一场回放，变成一份清晰的笔记</h2><p>粘贴链接开始。完成后，你可以按话题阅读观点，<br/>也可以从逐字稿的时间戳跳回原视频。</p><div className="mini-empty-features"><span><Check size={15}/> 原文可追溯</span><span><Check size={15}/> 逐字稿可导出</span><span><Check size={15}/> 转录缓存可复用</span></div></section> : <>
          <section className="mini-progress-card"><div className="mini-section-head"><div className="mini-status-heading"><span className={'mini-status-icon '+(task.status === 'FAILED' ? 'error' : '')}>{task.status === 'FAILED' ? <CircleAlert size={20}/> : task.status === 'SUCCESS' ? <Check size={20}/> : <Loader2 size={20} className="mini-spin"/>}</span><div><h2>{task.status === 'FAILED' ? '处理遇到了问题' : task.status === 'SUCCESS' ? '整理完成' : labels[task.status] || '正在处理'}</h2><p>{task.status === 'FAILED' ? '已完成的缓存会保留，可以重试。' : task.status === 'SUCCESS' ? '现在可以阅读、核对和导出这份笔记。' : progress?.message || task.message || '任务已提交，正在等待处理。'}</p></div></div><span className="mini-elapsed"><Clock3 size={14}/>{time(progress?.elapsed_seconds || 0)}</span></div>
            {task.status !== 'FAILED' && <div className="mini-stages">{stages.map((name,i) => <span key={name} className={i === stageIndex ? 'current' : i < stageIndex ? 'complete' : ''}><i>{i < stageIndex ? <Check size={11}/> : i+1}</i>{name}</span>)}</div>}
            {progress && <div className="mini-telemetry" aria-live="polite"><div className="mini-progress-line"><span>{progress.download_file ? '文件：'+progress.download_file : progress.model || '任务进度'}</span><strong>{typeof progress.percent === 'number' ? progress.percent.toFixed(1)+'%' : active ? '处理中' : ''}</strong></div><div className={'mini-progress-track ' + (active && typeof progress.percent !== 'number' ? 'indeterminate' : '')}><span style={{width: typeof progress.percent === 'number' ? Math.max(0,Math.min(100,progress.percent))+'%' : task.status === 'SUCCESS' ? '100%' : '0%'}}/></div><div className="mini-stats"><span><Cpu size={13}/>{progress.device === 'cuda' ? 'NVIDIA GPU' : progress.device === 'cpu' ? 'CPU' : progress.device === 'API' ? '在线总结' : progress.requested_device === 'cuda' ? 'GPU · 待加载' : '准备中'}</span>{progress.model && <span>{progress.model}</span>}{progress.compute_type && <span>{progress.compute_type}</span>}{progress.total_bytes ? <span>{((progress.downloaded_bytes || 0)/1048576).toFixed(1)} / {(progress.total_bytes/1048576).toFixed(1)} MB</span> : null}{progress.total_seconds ? <span>已识别 {time(progress.processed_seconds || 0)} / {time(progress.total_seconds)}</span> : null}<span>本阶段 {time(progress.stage_elapsed_seconds || 0)}</span></div>{progress.download_source && <p className="mini-progress-note">下载源：{progress.download_source}</p>}<p className="mini-progress-note">百分比对应当前步骤；下载连接重试会保留断点。</p></div>}
            {task.status === 'FAILED' && <div className="mini-failure"><p>{task.message || '处理失败，请重试。'}</p>{progress?.can_reset_model_download && <button className="mini-secondary" disabled={busy} onClick={clearAndRetry}><RotateCcw size={14}/>清理未完成下载并重试</button>}</div>}
          </section>
          <section className="mini-result"><div className="mini-result-heading"><div><p className="mini-eyebrow">YOUR NOTES</p><h2>{title}</h2></div><button className="mini-icon-button" title="重新总结或重试" aria-label="重新总结或重试" disabled={busy || !!active} onClick={() => submit(true)}><RotateCcw size={16}/></button></div>{task.summaryStale&&<p className="mini-correction-notice">逐字稿已校正。请点击右上角重新总结，更新摘要中的型号。</p>}<div className="mini-tabs-row"><div role="tablist" aria-label="笔记内容"><button role="tab" aria-selected={tab==='summary'} className={tab==='summary'?'chosen':''} onClick={() => setTab('summary')}><FileText size={15}/>观点摘要</button><button role="tab" aria-selected={tab==='transcript'} className={tab==='transcript'?'chosen':''} onClick={() => setTab('transcript')}><AudioLines size={15}/>逐字稿 {transcript.length ? <small>{transcript.length}</small> : null}</button></div>{transcript.length>0&&!active&&<button className="mini-export" onClick={()=>setCorrecting(true)}>校正术语</button>}<button className="mini-export" disabled={tab==='summary' ? !markdown : !transcript.length} onClick={() => download(tab==='summary'?'观点摘要.md':'逐字稿.txt', tab==='summary'?markdown:transcriptText)}><Download size={14}/>导出{tab==='summary'?' Markdown':' TXT'}</button></div><div className="mini-result-body" key={tab}>{tab==='summary' ? markdown ? <article className="mini-markdown"><ReactMarkdown>{markdown}</ReactMarkdown></article> : <div className="mini-result-placeholder"><FileText size={25}/><h3>观点正在路上</h3><p>完成处理后，摘要会出现在这里。<br/>不确定的型号、数字和说话人会标注待核对。</p></div> : transcript.length ? <div className="mini-transcript">{transcript.map((segment,i) => <p key={i}><a target="_blank" rel="noreferrer" href={'https://www.bilibili.com/video/'+(task.audioMeta?.video_id||'').replace('_p','?p=')+((task.audioMeta?.video_id||'').includes('_p')?'&':'?')+'t='+Math.floor(segment.start)}>{time(segment.start)}</a><span>{segment.text}</span></p>)}</div> : <div className="mini-result-placeholder"><AudioLines size={25}/><h3>等待逐字稿</h3><p>字幕提取或音频转录完成后可查看。</p></div>}</div></section>
        </>}
        <footer className="mini-footer">BiliNote Mini <span>为认真听过的内容，留一份可回看的记录。</span></footer>
      </div>
    </main>
  </div>
}
