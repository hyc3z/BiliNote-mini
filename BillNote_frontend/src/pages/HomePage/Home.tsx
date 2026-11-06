import { exportPdf } from '@/utils/exportPdf'
const sourcePlatform=(url:string)=>/https?:\/\/(?:www\.|m\.)?(?:youtube\.com|youtu\.be)\//i.test(url)?'youtube':/https?:\/\/(?:www\.)?instagram\.com\//i.test(url)?'instagram':'bilibili'
import CommentsPanel from './CommentsPanel'
import { useEffect, useState, useLayoutEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import SummaryReader from './SummaryReader'
import { useTaskStore } from '@/store/taskStore'
import { useModelStore } from '@/store/modelStore'
import { generateNote } from '@/services/note'
import request from '@/utils/request'
import { ArrowUpRight, Plus, Settings2, AudioLines, FileText, Download, RotateCcw, Check, CircleAlert, Loader2, Link2, Clock3, Search, MoreHorizontal, Trash2, BookOpen, Sparkles } from 'lucide-react'
import './mini.css'
import CorrectionDialog from '@/pages/CorrectionDialog'
import { useVideoSelection } from '@/hooks/useVideoSelection'


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
  const selection=useVideoSelection(url)
  const [model, setModel] = useState(localStorage.getItem('mini-model') || '')
  const [tab, setTab] = useState('summary')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [allVideos,setAllVideos]=useState(true)
  const [statusFilter,setStatusFilter]=useState('all')
  const [sortBy,setSortBy]=useState('newest')
  const [tagData,setTagData]=useState<{tags:Record<string,string[]>,videos:Record<string,string[]>}>({tags:{},videos:{}})
  const [newTags,setNewTags]=useState<string[]>([])
  useEffect(()=>{request.get('/tag_terms').then((data:any)=>setTagData(data)).catch(()=>{})},[])
  async function bindTags(bvid:string,tags:string[]){try{const data:any=await request.post('/video_tags',{bvid,tags});setTagData(data)}catch(e:any){setError(e?.detail||e?.msg||'标签保存失败');throw e}}

  const managerScroll=useRef(0)
  function backToManager(){setAllVideos(true);setError('');requestAnimationFrame(()=>window.scrollTo(0,managerScroll.current))}
  const [chapterQuery,setChapterQuery]=useState('')
  const [chapterIds,setChapterIds]=useState<string[]>([])
  const readerRef=useRef<HTMLDivElement>(null)
  const chapterListRef=useRef<HTMLDivElement>(null)
  const chapterFrame=useRef(0)
  const switchToken=useRef(0)
  useEffect(()=>{
    const list=chapterListRef.current
    const card=list?.querySelector<HTMLElement>('.mini-chapter-card.current')
    if(!list||!card)return
    const start=list.scrollTop
    const target=Math.max(0,Math.min(list.scrollHeight-list.clientHeight,start+card.getBoundingClientRect().top-list.getBoundingClientRect().top-list.clientHeight/2+card.offsetHeight/2))
    const began=performance.now()
    const tick=(now:number)=>{const t=Math.min(1,(now-began)/700);const ease=t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2;list.scrollTop=start+(target-start)*ease;if(t<1)chapterFrame.current=requestAnimationFrame(tick)}
    chapterFrame.current=requestAnimationFrame(tick)
    return()=>cancelAnimationFrame(chapterFrame.current)
  },[store.currentTaskId,allVideos,chapterQuery])
  useEffect(()=>{
    const node=readerRef.current
    const animation=node?.animate([{opacity:0,transform:'translateY(6px)'},{opacity:1,transform:'translateY(0)'}],{duration:320,easing:'ease-out'})
    return()=>animation?.cancel()
  },[store.currentTaskId,tab,allVideos])
  const [readerPane,setReaderPane]=useState('notes')
  useLayoutEffect(()=>{
    const node=readerRef.current
    if(!node)return
    const key='mini-reader:'+store.currentTaskId+':'+tab
    node.scrollTop=Number(localStorage.getItem(key)||0)
    const save=()=>localStorage.setItem(key,String(node.scrollTop))
    node.addEventListener('scroll',save,{passive:true})
    return()=>{save();node.removeEventListener('scroll',save)}
  },[store.currentTaskId,tab,allVideos])
  const [correcting,setCorrecting]=useState(false)
  const [library, setLibrary] = useState<any[]>([])
  const [searchIds,setSearchIds]=useState<string[]>([])
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
    const timer = setTimeout(() => { request.get('/library', {params:{q:query}}).then((rows:any) => {if(!cancelled){setSearchIds(rows.map((r:any)=>r.task_id));if(!query)setLibrary(rows);setSearchError('')}}).catch(() => {if(!cancelled)setSearchError('本地资料库暂时无法连接')}) }, 200)
    return () => { cancelled=true; clearTimeout(timer) }
  }, [query, store.tasks.filter(t => t.status === 'SUCCESS').length])
  async function openSaved(row:any) {
    try {
      const result:any = await request.get('/library/'+row.task_id)
      if(!store.tasks.some(t=>t.id===row.task_id)) store.addPendingTask(row.task_id,sourcePlatform(row.source),{video_url:row.source,platform:sourcePlatform(row.source),quality:'medium',model_name:'',provider_id:''} as any)
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
  const records:any[]=[...store.tasks.map(t=>({id:t.id,title:t.audioMeta?.title||'',source:t.formData.video_url,status:t.status,created:t.createdAt,task:t})),...library.filter(r=>!store.tasks.some(t=>t.id===r.task_id)).map(r=>({id:r.task_id,title:r.title,source:r.source,status:'SUCCESS',created:r.saved_at,duration:r.duration,saved:r}))]
  const groups:any[]=Array.from(records.reduce<Map<string,any>>((map:Map<string,any>,r)=>{
    const bv=(r.source||r.task?.audioMeta?.video_id||'').match(/BV[0-9A-Za-z]{10}/i)?.[0]||r.id
    const g=map.get(bv)||{bv,title:r.task?.formData?.group_title||r.title||bv,parts:[],created:r.created}
    g.parts.push(r);if(r.created>g.created)g.created=r.created;map.set(bv,g);return map
  },new Map()).values()).sort((a:any,b:any)=>String(b.created).localeCompare(String(a.created)))
  const task = store.tasks.find(t => t.id === store.currentTaskId)
  const group=groups.find(g=>g.parts.some((p:any)=>p.id===task?.id))
  const matches=(g:any)=>!query||g.parts.some((p:any)=>searchIds.includes(p.id))||[g.bv,g.title,...g.parts.map((p:any)=>p.title+' '+(p.task?.audioMeta?.raw_info?.owner?.name||'')+' '+(typeof p.task?.markdown==='string'?p.task.markdown:'' )+' '+(p.task?.transcript?.full_text||''))].join(' ').toLowerCase().includes(query.toLowerCase())
  async function openPart(p:any){
    const token=++switchToken.current
    if(p.id===store.currentTaskId&&!allVideos)return
    if(allVideos)managerScroll.current=window.scrollY
    const node=readerRef.current
    if(node&&!allVideos){
      const fade=node.animate([{opacity:1},{opacity:0}],{duration:160,easing:'ease-in'})
      try{await fade.finished}catch{}
      if(token!==switchToken.current)return
    }
    setReaderPane('notes');setAllVideos(false);setError('')
    if(p.saved)await openSaved(p.saved)
    else {store.setCurrentTask(p.id);if(p.status==='SUCCESS'&&!p.task?.markdown)await openSaved({task_id:p.id,source:p.source})}
  }
  async function retryParts(ids:string[]){
    if(!selected){setError('请先配置总结模型');return}
    setBusy(true);setError('')
    try {for(const id of ids){const p=records.find(p=>p.id===id);if(!p||!['SUCCESS','FAILED'].includes(p.status))continue
      await generateNote({video_url:p.source,platform:sourcePlatform(p.source),quality:'medium',model_name:selected.model_name,provider_id:selected.provider_id,format:['link'],link:true,style:'minimal',grid_size:[],task_id:id} as any)
      if(!store.tasks.some(t=>t.id===id))store.addPendingTask(id,'bilibili',{video_url:p.source})
      store.updateTaskContent(id,{status:'PENDING',message:''})
    }}catch(e:any){setError(e?.detail||e?.msg||'提交失败，已提交的任务会继续处理')}finally{setBusy(false)}
  }
  const orderedParts:any[]=group?[...group.parts].sort((a:any,b:any)=>Number(a.source.match(/[?&]p=(\d+)/)?.[1]||1)-Number(b.source.match(/[?&]p=(\d+)/)?.[1]||1)):[]
  const currentIndex=orderedParts.findIndex(p=>p.id===task?.id)
  const reading=!!task&&!allVideos
  const groupStatus=(g:any)=>g.parts.every((p:any)=>p.status==='SUCCESS')?'done':g.parts.some((p:any)=>!['SUCCESS','FAILED'].includes(p.status))?'working':'failed'
  const visibleGroups=groups.filter(matches).filter(g=>statusFilter==='all'||groupStatus(g)===statusFilter).sort((a,b)=>sortBy==='title'?a.title.localeCompare(b.title,'zh-CN'):sortBy==='oldest'?String(a.created).localeCompare(String(b.created)):String(b.created).localeCompare(String(a.created)))
  async function openGroup(g:any){const last=localStorage.getItem('mini-last:'+g.bv);setChapterQuery('');setChapterIds([]);await openPart(g.parts.find((p:any)=>p.id===last)||g.parts.find((p:any)=>p.status==='SUCCESS')||g.parts[0])}
  useEffect(()=>{if(group&&task)localStorage.setItem('mini-last:'+group.bv,task.id)},[task?.id,group?.bv])
  const markdown = typeof task?.markdown === 'string' ? task.markdown : task?.markdown?.[0]?.content || ''
  const active = task && !['SUCCESS', 'FAILED'].includes(task.status)
  const selected = modelList.find(m => String(m.id) === String(model)) || modelList[0]
  async function submit(retry = false) {
    setError('')
    if (!selected) { setError('请先在设置中配置并启用一个文字模型。'); return }
    if (retry && !task) return
    const input = (retry ? task!.formData.video_url : url).trim()
    if (!input) { setError('请输入 B 站链接或 BV 号。'); return }
    if(!retry && sourcePlatform(input)==='bilibili' && !selection.data){selection.retry();return}
    if(!retry && sourcePlatform(input)==='bilibili' && (!selection.keys.length || selection.keys.length>60)){setError('请选择 1–60 个视频分 P。');return}
    setBusy(true)
    const payload = { video_url: input, platform: sourcePlatform(input), quality: 'medium', model_name: selected.model_name, provider_id: selected.provider_id, format: ['link'], link: true, style: 'minimal', grid_size: [] }
    try {
      if(!retry && sourcePlatform(input)!=='bilibili'){
        const result:any=await generateNote(payload);store.addPendingTask(result.task_id,payload.platform,payload);setAllVideos(false)
      } else if(retry) {
        await generateNote({ ...payload, task_id: task!.id })
        store.updateTaskContent(task!.id, { status: 'PENDING', formData: payload, message: '' } as any)
      } else {
        for(const bv of new Set(selection.data!.parts.filter(p=>selection.keys.includes(p.key)).map(p=>p.bvid)))await bindTags(bv,newTags)
        const batch:any=await request.post('/prepare_selection',{video_url:input,keys:selection.keys,model_name:selected.model_name,provider_id:String(selected.provider_id)},{timeout:120000})
        for(const part of [...batch.parts].reverse()) {
          const current=useTaskStore.getState()
          if(!current.tasks.some(t=>t.id===part.task_id)) current.addPendingTask(part.task_id,'bilibili',{...payload,video_url:part.source,group_title:selection.data?.kind==='pages'?selection.data.title:part.title})
          const added=useTaskStore.getState().tasks.find(t=>t.id===part.task_id)!
          current.updateTaskContent(part.task_id,{status:part.state==='SUCCESS'?'SUCCESS':part.state==='RUNNING'?'RUNNING':'PENDING',audioMeta:{...added.audioMeta,title:part.title,video_id:part.bvid+'_p'+part.part},message:part.reused?'复用已有笔记或任务':''})
          if(part.state==='SUCCESS') {
            const saved:any=await request.get('/library/'+part.task_id)
            current.updateTaskContent(part.task_id,{markdown:saved.markdown,transcript:saved.transcript,audioMeta:saved.audio_meta,summaryStale:!!saved.summary_stale})
          }
        }
        if(batch.parts.length)store.setCurrentTask(batch.parts[0].task_id)
      }
    } catch (e: any) { setError(e?.detail || e?.msg || '提交失败，请检查后端连接。') }
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
  const transcript = task?.transcript?.segments || []
  const transcriptText = transcript.map(s => '[' + time(s.start) + '] ' + s.text).join('\n')
  const title = task?.audioMeta?.title || '回放整理'
  return <div className="mini-app mini-vault">
    {correcting && task && <CorrectionDialog taskId={task.id} onClose={()=>setCorrecting(false)} onApply={transcript=>{store.updateTaskContent(task.id,{transcript,summaryStale:true});}}/>}
    {menu && <div className="mini-context" role="menu" aria-label="任务操作" style={{left:menu.x,top:menu.y}} onClick={event=>event.stopPropagation()}><p>任务操作</p><button role="menuitem" disabled={store.tasks.some(t=>t.id===menu.id && !['FAILED','SUCCESS'].includes(t.status))} onClick={()=>deleteTask(menu.id)}><Trash2 size={15}/>删除这条记录</button><small>移除笔记与任务文件，保留共享缓存</small></div>}
    <main className="mini-main">
      <header className="mini-topbar vault-topbar"><button className="vault-brand" onClick={backToManager}><span><AudioLines size={21}/></span>BiliNote <em>mini</em></button><nav aria-label="页面导航"><button onClick={backToManager}>回放笔记</button><span>/</span><strong>{allVideos?'笔记管理':reading?'阅读工作台':'新建整理'}</strong></nav><Link className="vault-settings" to="/settings"><Settings2 size={17}/><span>模型与设置</span></Link></header>
      <div className={"mini-content "+(reading?"mini-reading pane-"+readerPane+(orderedParts.length===1?" single-chapter":""):allVideos?"vault-manager":"vault-create")}>
        {reading&&<div className="mini-reader-switch" role="tablist" aria-label="阅读布局"><button role="tab" aria-selected={readerPane==='notes'} onClick={()=>setReaderPane('notes')}>笔记</button><button role="tab" aria-selected={readerPane==='chapters'} onClick={()=>setReaderPane('chapters')}>章节目录 · {orderedParts.length}</button></div>}
        {!allVideos&&!reading&&<><button className="vault-back" onClick={backToManager}>← 返回笔记管理</button><div className="mini-heading"><div><p className="mini-eyebrow">LESS WATCHING, MORE UNDERSTANDING</p><h1>长回放，<br className="mini-editorial-break"/><span>留下有用的观点。</span></h1><p>从视频链接到可回看的笔记，保留依据、限定条件和时间戳。</p></div><span className="mini-heading-icon"><Sparkles size={34}/><i>MAKE IT<br/>WORTH KEEPING.</i></span></div></>}
        {!allVideos&&<form className="mini-input-card" onSubmit={e => { e.preventDefault(); submit() }}><div className="mini-link-input"><Link2 size={19}/><input aria-label="B站链接或BV号" placeholder="粘贴 B 站、YouTube、Instagram 视频链接" value={url} disabled={busy} onChange={e => setUrl(e.target.value)}/><button className="mini-primary" disabled={busy || selection.loading || (!!selection.data && (!selection.keys.length || selection.keys.length>60))}>{busy ? <Loader2 size={16} className="mini-spin"/> : <Plus size={16}/>}{selection.loading?'正在解析':selection.data?'整理选中 '+selection.keys.length+' 项':sourcePlatform(url)!=='bilibili'?'开始整理':'解析选集'}</button></div><div className="mini-input-footer"><span>字幕优先 · 无字幕时本地转录</span><label>总结模型 <select aria-label="总结模型" value={selected?.id || ''} onChange={e => {setModel(e.target.value); localStorage.setItem('mini-model',e.target.value)}}><option value="" disabled>前往设置添加模型</option>{modelList.map(m => <option key={m.id} value={m.id}>{m.model_name}</option>)}</select></label></div></form>}
        {!allVideos&&!reading&&<div className="video-tag-picker"><span>内容标签 · 仅使用所选标签词表</span>{Object.keys(tagData.tags).map(t=><label key={t}><input type="checkbox" checked={newTags.includes(t)} onChange={e=>setNewTags(e.target.checked?[...newTags,t]:newTags.filter(v=>v!==t))}/>{t}</label>)}<Link to="/settings">维护词表 ↗</Link></div>}
        {!allVideos&&(selection.loading || selection.error || selection.data) && <section className="mini-selection" aria-label="视频选集">
          {selection.loading ? <p className="mini-selection-loading"><Loader2 size={16} className="mini-spin"/>正在读取选集标题与时长…</p> : selection.error ? <div role="alert"><p>{selection.error}</p><button className="mini-secondary" onClick={selection.retry}>重新解析</button></div> : selection.data && <>
            <header><div><p className="mini-eyebrow">CHOOSE YOUR CHAPTERS</p><h2>{selection.data.title}</h2><p>{selection.data.kind==='collection'?'视频合集':'视频选集'} · 共 {selection.data.parts.length} 项 · 已选 {selection.keys.length} 项 · {time(selection.data.parts.filter(p=>selection.keys.includes(p.key)).reduce((sum,p)=>sum+(p.duration||0),0))}</p></div><div className="mini-selection-actions"><button type="button" disabled={busy} onClick={()=>selection.setKeys(selection.data!.parts.map(p=>p.key))}>全选</button><button type="button" disabled={busy} onClick={()=>selection.setKeys([])}>清空</button></div></header>
            <div className="mini-selection-list">{selection.data.parts.map((part,index)=><label key={part.key} className={selection.keys.includes(part.key)?'checked':''}><input type="checkbox" disabled={busy} checked={selection.keys.includes(part.key)} onChange={e=>selection.setKeys(e.target.checked?[...selection.keys,part.key]:selection.keys.filter(k=>k!==part.key))}/><span className="mini-selection-number">{String(index+1).padStart(2,'0')}</span><span className="mini-selection-title" title={part.title}>{part.title}</span><time>{time(part.duration||0)}</time></label>)}</div>
            <footer>{selection.keys.length>60?'一次最多处理 60 项，请取消部分选择。':'默认全选，可取消不需要的内容。每项单独保存，依次处理；已有笔记直接复用。'}</footer>
          </>}
        </section>}
        {error && <div role="alert" className="mini-error"><CircleAlert size={17}/>{error}</div>}
        {reading&&<button className="vault-reader-back" onClick={backToManager}>← 返回笔记管理</button>}
        {allVideos&&<section className="vault-library">
          <div className="vault-intro"><div><p className="vault-kicker">YOUR KNOWLEDGE, ON REPEAT.</p><h1>好内容，<span>留得住。</span></h1><p>从一段视频，到随时可读的个人资料库。</p></div><button className="vault-add" onClick={()=>{store.setCurrentTask(null);setAllVideos(false);setUrl('');setError('')}}><Plus size={18}/>新建整理</button></div>
          <div className="vault-stats"><span><strong>{groups.length}</strong> 个视频</span><span><strong>{groups.filter(g=>groupStatus(g)==='done').length}</strong> 已就绪</span><span><i/><strong>{groups.filter(g=>groupStatus(g)==='working').length}</strong> 整理中</span><span>本地保存 · 随时回看</span></div>
          <div className="vault-toolbar"><label><Search size={17}/><input aria-label="搜索笔记" placeholder="搜索标题、BV、UP 主或笔记内容" value={query} onChange={e=>setQuery(e.target.value)}/></label><select aria-label="筛选状态" value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}><option value="all">全部状态</option><option value="done">已完成</option><option value="working">整理中</option><option value="failed">需重试</option></select><select aria-label="排序" value={sortBy} onChange={e=>setSortBy(e.target.value)}><option value="newest">最近添加</option><option value="oldest">最早添加</option><option value="title">标题 A–Z</option></select></div>
          {searchError&&<p role="alert">{searchError}</p>}
          <div className="vault-table" role="table" aria-label="笔记管理"><div className="vault-table-head" role="row"><span>视频 / 笔记</span><span>整体状态</span><span>视频总时长</span><span>添加时间</span><span/></div>{visibleGroups.map(g=>{const done=g.parts.filter((p:any)=>p.status==='SUCCESS').length;const state=groupStatus(g);const duration=g.parts.reduce((n:number,p:any)=>n+Number(p.task?.audioMeta?.duration||p.duration||0),0);return <div className="vault-row" role="row" key={g.bv}><button className="vault-title" onClick={()=>openGroup(g)}><span className={'vault-file '+state}><BookOpen size={23}/></span><span><strong>{g.title}</strong><small>{g.bv} <b>·</b> {g.parts.length} 个分 P</small></span></button><div className={'vault-status '+state}><span><i/>{state==='done'?'已完成':state==='working'?'整理中':'需重试'}<small>{done}/{g.parts.length}</small></span><progress aria-label={g.title+' 整体进度'} value={done} max={g.parts.length}/></div><div className="vault-video-tags"><select aria-label={'设置标签 '+g.title} value="" onChange={e=>{if(e.target.value)bindTags(g.bv,[...new Set([...(tagData.videos[g.bv]||[]),e.target.value])]).catch(()=>{})}}><option value="">＋ 标签</option>{Object.keys(tagData.tags).map(t=><option key={t}>{t}</option>)}</select>{(tagData.videos[g.bv]||[]).map(t=><button key={t} title={'移除标签 '+t} onClick={()=>bindTags(g.bv,tagData.videos[g.bv].filter(v=>v!==t)).catch(()=>{})}>{t} ×</button>)}</div><span className="vault-duration">{duration?time(duration):'待获取'}</span><time>{new Date(g.created).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}</time><button className="vault-enter" aria-label={'打开 '+g.title} onClick={()=>openGroup(g)}><ArrowUpRight size={19}/></button></div>})}</div>
          {!visibleGroups.length&&<div className="vault-empty"><BookOpen size={32}/><h2>{groups.length?'没有匹配的笔记':'你的下一次灵感，从这里开始'}</h2><p>{groups.length?'试试其他关键词或状态筛选。':'点击新建整理，添加第一条 B 站链接。'}</p></div>}
          <p className="vault-bottom-note">{visibleGroups.length} 个视频 · 点击标题打开笔记 <span>LESS WATCHING. MORE KEEPING.</span></p>
        </section>}
        {!allVideos&&group&&<section className="mini-selection" aria-label="章节目录"><header><div><p className="mini-eyebrow">VIDEO CHAPTERS</p><h2>{group.title}</h2><p>{group.bv} · 共 {group.parts.length} 个分 P · 完成 {group.parts.filter((p:any)=>p.status==='SUCCESS').length} · 处理中 {group.parts.filter((p:any)=>!['SUCCESS','FAILED','PENDING'].includes(p.status)).length} · 排队 {group.parts.filter((p:any)=>p.status==='PENDING').length} · 失败 {group.parts.filter((p:any)=>p.status==='FAILED').length}</p></div></header>
          <div className="mini-total-progress"><div><span>整体完成度</span><strong>{Math.round(group.parts.filter((p:any)=>p.status==='SUCCESS').length/group.parts.length*100)}%</strong></div><progress className="mini-group-progress" value={group.parts.filter((p:any)=>p.status==='SUCCESS').length} max={group.parts.length}/></div>
          <div className="mini-chapter-tools"><input aria-label="搜索章节" placeholder="搜索分 P 标题或编号" value={chapterQuery} onChange={e=>setChapterQuery(e.target.value)}/><button onClick={()=>setChapterIds(group.parts.filter((p:any)=>['SUCCESS','FAILED'].includes(p.status)).map((p:any)=>p.id))}>选择可整理项</button><button onClick={()=>setChapterIds([])}>清空</button><button disabled={busy||!group.parts.some((p:any)=>p.status==='FAILED')} onClick={()=>retryParts(group.parts.filter((p:any)=>p.status==='FAILED').map((p:any)=>p.id))}>重试失败项</button><button disabled={busy||!chapterIds.length} onClick={()=>retryParts(chapterIds)}>重新整理选中 {chapterIds.length} 项</button></div>
          <div className="mini-chapter-list" ref={chapterListRef} onWheel={()=>cancelAnimationFrame(chapterFrame.current)} onTouchStart={()=>cancelAnimationFrame(chapterFrame.current)}>{orderedParts.filter((p:any)=>(p.title+' P'+(p.source.match(/[?&]p=(\d+)/)?.[1]||1)).toLowerCase().includes(chapterQuery.toLowerCase())).map((p:any)=>{
            const done=p.status==='SUCCESS',failed=p.status==='FAILED',queued=p.status==='PENDING'
            const working=!done&&!failed&&!queued
            const percent=typeof p.task?.progress?.percent==='number'?Math.max(0,Math.min(100,p.task.progress.percent)):null
            const value=done?100:percent??0
            return <div key={p.id} className={'mini-chapter-card '+(p.id===task?.id?'current ':'')+(done?'is-done':failed?'is-failed':working?'is-working':'is-queued')}>
              <input type="checkbox" aria-label={'选择 '+p.title} disabled={!['SUCCESS','FAILED'].includes(p.status)||busy} checked={chapterIds.includes(p.id)} onChange={e=>setChapterIds(e.target.checked?[...chapterIds,p.id]:chapterIds.filter(id=>id!==p.id))}/>
              <button className="mini-chapter-open" onClick={()=>openPart(p)} aria-current={p.id===task?.id?'true':undefined}>
                <span className="mini-chapter-top"><span className="mini-chapter-number">P{p.source.match(/[?&]p=(\d+)/)?.[1]||1}</span><span className="mini-chapter-badge">{done?<Check size={11}/>:working?<Loader2 size={11} className="mini-spin"/>:failed?<CircleAlert size={11}/>:<Clock3 size={11}/>} {labels[p.status]||p.status}</span></span>
                <strong title={p.title}>{p.title||group.bv}</strong>
                <span className="mini-chapter-meter-label"><span>{done?'笔记已就绪':failed?'可重试 · 缓存保留':queued?'等待处理':percent===null?'正在处理':'当前阶段'}</span><span>{done?'100%':working&&percent!==null?percent.toFixed(0)+'%':queued?'排队中':failed?'失败':'进行中'}</span></span>
                <span className={'mini-chapter-meter '+(working&&percent===null?'is-indeterminate':'')} role="progressbar" aria-label={p.title+' '+(labels[p.status]||p.status)} aria-valuemin={0} aria-valuemax={100} aria-valuenow={working&&percent===null?undefined:value}><span style={{width:value+'%'}}/></span>
              </button>
              <button className="mini-chapter-more" aria-label={'更多操作 '+p.title} onClick={e=>openMenu(e,p.id)}><MoreHorizontal size={16}/></button>
            </div>
          })}</div>
          <footer>同一 BV 合并显示；再次提交会补充缺失分 P，已有结果复用。重新整理仅处理选中的已完成或失败章节。</footer>
        </section>}
        {allVideos ? null : !task ? <section className="mini-empty"><div className="mini-empty-symbol"><FileText size={30}/></div><h2>把一场回放，变成一份清晰的笔记</h2><p>粘贴链接开始。完成后，你可以按话题阅读观点，<br/>也可以从逐字稿的时间戳跳回原视频。</p><div className="mini-empty-features"><span><Check size={15}/> 原文可追溯</span><span><Check size={15}/> 逐字稿可导出</span><span><Check size={15}/> 转录缓存可复用</span></div></section> : <>
          <section className="mini-overall-bar" aria-label="视频整体进度"><div><span>整体进度</span><strong>{group?group.parts.filter((p:any)=>p.status==='SUCCESS').length:task.status==='SUCCESS'?1:0} / {group?.parts.length||1} 已完成</strong></div><progress max={group?.parts.length||1} value={group?group.parts.filter((p:any)=>p.status==='SUCCESS').length:task.status==='SUCCESS'?1:0}/>{task.status==='FAILED'&&<div className="mini-failure"><p>{task.message||'当前章节处理失败，可在侧边卡片重试。'}</p>{task.progress?.can_reset_model_download&&<button className="mini-secondary" disabled={busy} onClick={clearAndRetry}>清理未完成下载并重试</button>}</div>}</section>
          <section className="mini-result"><div className="mini-result-heading"><div><p className="mini-eyebrow">YOUR NOTES</p><h2>{title}</h2><span className="source-tag">{{bilibili:'Bilibili',youtube:'YouTube',instagram:'Instagram'}[sourcePlatform(task.formData.video_url)]}</span></div><button className="mini-icon-button" title="重新总结或重试" aria-label="重新总结或重试" disabled={busy || !!active} onClick={() => submit(true)}><RotateCcw size={16}/></button></div>{task.summaryStale&&<p className="mini-correction-notice">逐字稿已校正。请点击右上角重新总结，更新摘要中的型号。</p>}<div className="mini-tabs-row"><div role="tablist" aria-label="笔记内容"><button role="tab" aria-selected={tab==='summary'} className={tab==='summary'?'chosen':''} onClick={() => setTab('summary')}><FileText size={15}/>摘要与原文</button><button role="tab" aria-selected={tab==='transcript'} className={tab==='transcript'?'chosen':''} onClick={() => setTab('transcript')}><AudioLines size={15}/>完整逐字稿 {transcript.length ? <small>{transcript.length}</small> : null}</button><button style={{display:sourcePlatform(task.formData.video_url)==='bilibili'?undefined:'none'}} role="tab" aria-selected={tab==='comments'} className={tab==='comments'?'chosen':''} onClick={()=>setTab('comments')}>评论区分析</button></div>{tab!=='comments'&&transcript.length>0&&!active&&<button className="mini-export" onClick={()=>setCorrecting(true)}>校正术语</button>}{tab==='summary'&&<button className="mini-export" disabled={!markdown} onClick={()=>{const article=readerRef.current?.querySelector<HTMLElement>('article.mini-markdown');if(article)exportPdf(article,title,task.formData.video_url).catch(e=>setError(e.message))}}>导出 PDF</button>}<button className="mini-export" style={{display:tab==='comments'?'none':undefined}} disabled={tab==='summary' ? !markdown : !transcript.length} onClick={() => download(tab==='summary'?'观点摘要.md':'逐字稿.txt', tab==='summary'?markdown:transcriptText)}><Download size={14}/>导出{tab==='summary'?' Markdown':' TXT'}</button></div><div className="mini-result-body" ref={readerRef} key={task.id+tab}>{tab==='comments'?<CommentsPanel bvid={(task.audioMeta?.video_id||task.formData.video_url).match(/BV[0-9A-Za-z]{10}/)?.[0]||''} model={selected}/>:tab==='summary' ? markdown ? <SummaryReader key={task.id} markdown={markdown} taskId={task.id} segments={transcript}/ > : <div className="mini-result-placeholder"><FileText size={25}/><h3>观点正在路上</h3><p>完成处理后，摘要会出现在这里。<br/>不确定的型号、数字和说话人会标注待核对。</p></div> : transcript.length ? <div className="mini-transcript">{transcript.map((segment,i) => <p key={i}><a target="_blank" rel="noreferrer" href={sourcePlatform(task.formData.video_url)!=='bilibili'?task.formData.video_url+(sourcePlatform(task.formData.video_url)==='youtube'?(task.formData.video_url.includes('?')?'&':'?')+'t='+Math.floor(segment.start):''):'https://www.bilibili.com/video/'+(task.audioMeta?.video_id||'').replace('_p','?p=')+((task.audioMeta?.video_id||'').includes('_p')?'&':'?')+'t='+Math.floor(segment.start)}>{time(segment.start)}</a><span>{segment.text}</span></p>)}</div> : <div className="mini-result-placeholder"><AudioLines size={25}/><h3>等待逐字稿</h3><p>字幕提取或音频转录完成后可查看。</p></div>}</div></section>
        </>}
        {reading&&<div className="mini-reader-dock" aria-label="章节导航"><div><small>当前阅读 · {currentIndex+1} / {orderedParts.length}</small><strong title={title}>{title}</strong></div><button disabled={currentIndex<=0} onClick={()=>openPart(orderedParts[currentIndex-1])}>上一章</button><button disabled={currentIndex<0||currentIndex>=orderedParts.length-1} onClick={()=>openPart(orderedParts[currentIndex+1])}>下一章</button><button onClick={()=>setReaderPane(readerPane==='chapters'?'notes':'chapters')}>目录</button><a href={task.formData.video_url} target="_blank" rel="noreferrer">原视频 ↗</a></div>}
        <footer className="mini-footer">BiliNote Mini <span>为认真听过的内容，留一份可回看的记录。</span></footer>
      </div>
    </main>
  </div>
}

