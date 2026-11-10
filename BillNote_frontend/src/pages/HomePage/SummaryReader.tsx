import { splitQuickTake } from '@/utils/quickTake'
import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'

function TimestampImage({src,alt}:{src?:string;alt?:string}) {
  const [failed,setFailed]=useState(false)
  const [attempt,setAttempt]=useState(0)
  return <span className="mini-frame">{failed?<button onClick={()=>{setFailed(false);setAttempt(n=>n+1)}}>截图读取失败，点击重试</button>:<img loading="lazy" src={src+(attempt?'?retry='+attempt:'')} alt={alt||'原片画面'} onError={()=>setFailed(true)}/>}<small>{alt}</small></span>
}
interface Segment {start:number;end:number;text:string}
const clock=(seconds:number)=>[Math.floor(seconds/3600),Math.floor(seconds/60)%60,Math.floor(seconds)%60].map(n=>String(n).padStart(2,'0')).join(':')
function originalAt(start:number,stamps:number[],segments:Segment[]){
  const next=stamps.find(t=>t>start)??Infinity
  return segments.filter(s=>s.end>start&&s.start<next)
}
export default function SummaryReader({markdown,taskId,segments=[]}:{markdown:string;taskId:string;segments?:Segment[]}) {
  const quickTake=splitQuickTake(markdown)
  const timestamps=(line:string)=>[...line.matchAll(/\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g)].flatMap(m=>{
    const query=m[2].match(/[?&]t=(\d+)/)
    if(query)return [Number(query[1])]
    const label=m[1].match(/原片\s*@\s*(\d+):(\d{2})(?::(\d{2}))?/)
    return label?[label[3]?Number(label[1])*3600+Number(label[2])*60+Number(label[3]):Number(label[1])*60+Number(label[2])]:[]
  })
  const stamps=[...new Set(timestamps(markdown))].sort((a,b)=>a-b)
  const lines=quickTake.body.split('\n')
  const inserts=new Map<number,number[]>()
  lines.forEach((line,index)=>{
    const times=timestamps(line)
    if(!times.length)return
    let end=index+1
    while(end<lines.length&&!/^#{1,6}\s/.test(lines[end])&&!timestamps(lines[end]).length)end++
    inserts.set(end-1,[...(inserts.get(end-1)||[]),...times])
  })
  const paired=lines.map((line,index)=>line+(inserts.get(index)||[]).map(t=>'\n\n![对应原文](/__transcript__/'+t+')\n').join('')).join('\n')

  const illustrated=paired.split('\n').map(line=>{
    const matches=[...line.matchAll(/\[([^\]]*)\]\((https?:\/\/[^\s)]+)\)/g)]
    const frames=[...new Set(matches.flatMap(m=>{
      const query=m[2].match(/[?&]t=(\d+)/)
      if(query)return [query[1]]
      const label=m[1].match(/原片\s*@\s*(\d+):(\d{2})(?::(\d{2}))?/)
      if(!label)return []
      return [String(label[3]?Number(label[1])*3600+Number(label[2])*60+Number(label[3]):Number(label[1])*60+Number(label[2]))]
    }))]
    return line+frames.map(seconds=>'\n\n![原片 '+Math.floor(Number(seconds)/60)+":"+String(Number(seconds)%60).padStart(2,'0')+' 的画面]('+(import.meta.env.VITE_API_BASE_URL||'/api')+'/tasks/'+taskId+'/frame/'+seconds+')\n').join('')
  }).join('\n')

  const article=useRef<HTMLElement>(null)
  const navigation=useRef<HTMLElement>(null)
  const animation=useRef(0)
  const navigating=useRef(false)
  const navAnimation=useRef(0)
  useEffect(()=>()=>{cancelAnimationFrame(animation.current);cancelAnimationFrame(navAnimation.current)},[])
  const [headings,setHeadings]=useState<{id:string,title:string,level:number}[]>([])
  const [active,setActive]=useState('')
  const [query,setQuery]=useState('')
  const [expanded,setExpanded]=useState(false)
  useEffect(()=>{
    const nav=navigation.current
    const button=nav?.querySelector<HTMLElement>('[aria-current="location"]')
    if(!nav||!button)return
    cancelAnimationFrame(navAnimation.current)
    const start=nav.scrollTop
    const target=Math.max(0,Math.min(nav.scrollHeight-nav.clientHeight,start+button.getBoundingClientRect().top-nav.getBoundingClientRect().top-nav.clientHeight/2+button.offsetHeight/2))
    const began=performance.now()
    const tick=(now:number)=>{
      const t=Math.min(1,(now-began)/650)
      const eased=t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2
      nav.scrollTop=start+(target-start)*eased
      if(t<1)navAnimation.current=requestAnimationFrame(tick)
    }
    navAnimation.current=requestAnimationFrame(tick)
    return()=>cancelAnimationFrame(navAnimation.current)
  },[active,query,expanded])
  useEffect(()=>{
    const node=article.current
    const root=node?.closest('.mini-result-body') as HTMLElement|null
    if(!node||!root)return
    const elements=Array.from(node.querySelectorAll<HTMLElement>('h1,h2,h3,h4'))
    setHeadings(elements.map((el,i)=>{el.id='summary-section-'+i;return {id:el.id,title:el.innerText,level:Number(el.tagName.slice(1))}}))
    const update=()=>{
      if(navigating.current)return
      const top=root.getBoundingClientRect().top+48
      let current=elements[0]?.id||''
      for(const el of elements){if(el.getBoundingClientRect().top<=top)current=el.id;else break}
      setActive(current)
    }
    const interrupt=()=>{cancelAnimationFrame(animation.current);navigating.current=false}
    update();root.addEventListener('scroll',update,{passive:true})
    root.addEventListener('wheel',interrupt,{passive:true});root.addEventListener('touchstart',interrupt,{passive:true})
    return()=>{root.removeEventListener('scroll',update);root.removeEventListener('wheel',interrupt);root.removeEventListener('touchstart',interrupt);cancelAnimationFrame(animation.current);navigating.current=false}
  },[markdown])
  function jump(id:string){
    const node=article.current?.querySelector<HTMLElement>('#'+id)
    const root=article.current?.closest('.mini-result-body') as HTMLElement|null
    if(!node||!root)return
    cancelAnimationFrame(animation.current)
    setActive(id);setExpanded(false)
    node.tabIndex=-1;node.focus({preventScroll:true})
    const start=root.scrollTop
    const target=Math.max(0,Math.min(root.scrollHeight-root.clientHeight,start+node.getBoundingClientRect().top-root.getBoundingClientRect().top-22))
    navigating.current=true
    const began=performance.now(),duration=Math.min(1200,700+Math.abs(target-start)*.1)
    const tick=(now:number)=>{
      const t=Math.min(1,(now-began)/duration)
      const eased=t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2
      root.scrollTop=start+(target-start)*eased
      if(t<1)animation.current=requestAnimationFrame(tick)
      else navigating.current=false
    }
    animation.current=requestAnimationFrame(tick)

  }
  return <div className="summary-workspace"><article className="mini-markdown" ref={article}>{quickTake.summary&&<section className="quick-take-card" aria-label="整片省流"><strong>省流：</strong><ReactMarkdown>{quickTake.summary}</ReactMarkdown></section>}<ReactMarkdown components={{img:({src,alt})=>{
    if(src?.startsWith('/__transcript__/')){
      const start=Number(src.split('/').pop()),original=originalAt(start,stamps,segments)
      return <span className="paired-original"><span className="paired-original-label">原始文字稿 · {clock(start)}{original.length?' — '+clock(original[original.length-1].end):''}</span>{original.length?original.map((s,i)=><span className="paired-original-line" key={i}><small>{clock(s.start)}</small><em>{s.text}</em></span>):<em>此时间范围暂无匹配原文。</em>}</span>
    }
    return <TimestampImage src={src} alt={alt}/>
  }}}>{illustrated}</ReactMarkdown></article>{headings.length>0&&<aside className={'summary-outline '+(expanded?'expanded':'')} aria-label="观点目录"><button className="outline-toggle" aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>观点目录 <span>{headings.length}</span></button><div className="outline-content"><p>本篇大纲 <span>{headings.length} 个标题</span></p><input aria-label="搜索观点目录" placeholder="查找观点…" value={query} onChange={e=>setQuery(e.target.value)}/><nav ref={navigation}>{headings.filter(h=>h.title.toLowerCase().includes(query.toLowerCase())).map(h=><button key={h.id} className={active===h.id?'active':''} aria-current={active===h.id?'location':undefined} style={{paddingLeft:12+Math.max(0,h.level-2)*10}} onClick={()=>jump(h.id)}>{h.title}</button>)}</nav>{!headings.some(h=>h.title.toLowerCase().includes(query.toLowerCase()))&&<small>没有匹配的标题</small>}</div></aside>}</div>
}

