import { useEffect, useState } from 'react'
import request from '@/utils/request'
export interface VideoPart { key: string; bvid: string; cid: string; part: number; title: string; duration: number; source: string }
interface Selection { title: string; kind: string; parts: VideoPart[] }
export function useVideoSelection(url: string) {
  const [result,setResult]=useState<{input:string; data:Selection}|null>(null)
  const [keys,setKeys]=useState<string[]>([])
  const [loading,setLoading]=useState(false)
  const [error,setError]=useState('')
  const [attempt,setAttempt]=useState(0)
  const input=url.trim()
  useEffect(()=>{
    setResult(null);setKeys([]);setError('');setLoading(false)
    if(/^https?:\/\/(?:www\.|m\.)?(?:youtube\.com|youtu\.be|instagram\.com)\//i.test(input))return
    if(!/BV[0-9a-zA-Z]{10}(?![0-9a-zA-Z])/.test(input) && !/^https:\/\/b23\.tv\//.test(input)){if(attempt>0 && input)setError('请输入完整的 BV 号或 B 站视频链接');return}
    let current=true
    const controller=new AbortController()
    setLoading(true)
    const timer=setTimeout(async()=>{
      try {
        const data=await request.post<unknown,Selection>('/video_selection',{video_url:input},{signal:controller.signal,timeout:120000,suppressToast:true})
        if(current){setResult({input,data});setKeys(data.parts.map(p=>p.key))}
      } catch(e:any) { if(current)setError(e?.detail||e?.msg||'解析选集失败，请重试') }
      finally {if(current)setLoading(false)}
    },650)
    return()=>{current=false;clearTimeout(timer);controller.abort()}
  },[input,attempt])
  const data=result?.input===input?result.data:null
  return {data,keys,setKeys,loading,error,retry:()=>setAttempt(n=>n+1)}
}

