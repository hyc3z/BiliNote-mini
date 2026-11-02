import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useTaskPolling } from '@/hooks/useTaskPolling'
import { HomePage } from '@/pages/HomePage/Home'
import MiniSettings from '@/pages/MiniSettings'
export default function App() {
  useTaskPolling(3000)
  const [ready,setReady]=useState(false)
  const [attempt,setAttempt]=useState(0)
  const [failed,setFailed]=useState(false)
  useEffect(()=>{
    const controller=new AbortController()
    let active=true
    setFailed(false)
    fetch((import.meta.env.VITE_API_BASE_URL || '/api')+'/sys_check',{signal:controller.signal})
      .then(response=>response.json()).then(data=>{if(active){setReady(data.code===0);setFailed(data.code!==0)}})
      .catch(()=>{if(active)setFailed(true)})
    const timer=setTimeout(()=>controller.abort(),5000)
    return()=>{active=false;clearTimeout(timer);controller.abort()}
  },[attempt])
  if(!ready)return <main className="mini-settings-page"><h1>BiliNote Mini</h1><p>{failed?'后端尚未就绪，请先运行 start-mini.ps1。':'正在连接本地服务…'}</p>{failed&&<button onClick={()=>setAttempt(n=>n+1)}>重新连接</button>}</main>
  return <BrowserRouter><Routes><Route path="/" element={<HomePage/>}/><Route path="/settings/*" element={<MiniSettings/>}/><Route path="*" element={<Navigate to="/" replace/>}/></Routes></BrowserRouter>
}
