import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import request from '@/utils/request'
import { addModel, addProvider, updateProviderById } from '@/services/model'

export default function MiniSettings() {
  const [form, setForm] = useState({ base_url: '', api_key: '', model_name: '', cookie: '', whisper_model_size: 'small', device: 'cpu' })
  const [id, setId] = useState('')
  const [terms,setTerms]=useState('')
  useEffect(()=>{request.get('/terminology').then((data:any)=>setTerms(data.terms.join('、'))).catch(()=>{})},[])
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [ready, setReady] = useState(false)
  useEffect(() => {
    Promise.all([request.get('/get_all_providers'), request.get('/model_list'), request.get('/transcriber_config'), request.get('/get_downloader_cookie/bilibili'), request.get('/mini_preferences')]).then(([providers, models, transcriber, cookie, prefs]: any[]) => {
      const provider = providers.find((p: any) => p.name === 'Mini 默认模型')
      setId(provider?.id || '')
      setForm(f => ({ ...f, base_url: provider?.base_url || '', model_name: models.find((m: any) => m.provider_id === provider?.id)?.model_name || '', whisper_model_size: transcriber.whisper_model_size, cookie: cookie?.cookie || '', device: prefs.device }))
      setReady(true)
    }).catch(() => setMessage('设置读取失败，请刷新重试。'))
  }, [])
  const field = (name: keyof typeof form, value: string) => setForm(f => ({ ...f, [name]: value }))
  async function save(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setMessage('')
    try {
      let providerId = id
      if (id) await updateProviderById({ id, base_url: form.base_url, ...(form.api_key.trim() ? { api_key: form.api_key } : {}) })
      else { providerId = await addProvider({ name: 'Mini 默认模型', type: 'custom', base_url: form.base_url, api_key: form.api_key }) as any; setId(providerId) }
      await addModel({ provider_id: providerId, model_name: form.model_name })
      const models: any = await request.get('/model_list')
      const chosen = models.find((m: any) => m.provider_id === providerId && m.model_name === form.model_name)
      if (chosen) localStorage.setItem('mini-model', String(chosen.id))
      await request.post('/transcriber_config', { transcriber_type: 'fast-whisper', whisper_model_size: form.whisper_model_size })
      await request.post('/update_downloader_cookie', { platform: 'bilibili', cookie: form.cookie })
      await request.post('/mini_preferences', { device: form.device })
      await request.post('/terminology',{terms:terms.split(/[、,，\n]+/).map(t=>t.trim()).filter(Boolean)})
      setForm(f => ({ ...f, api_key: '' })); setMessage('设置已保存。返回首页即可开始整理。')
    } catch (e: any) { setMessage(e?.msg || '保存失败，请检查填写内容。') }
    finally { setBusy(false) }
  }
  return <main className="mini-settings-page"><header className="mb-6 flex justify-between"><div><p className="mini-eyebrow">PERSONAL WORKSPACE</p><h1 className="text-2xl font-semibold">模型与设置</h1></div><Link to="/">返回首页</Link></header>
    <form onSubmit={save} className="space-y-5">
      <label className="block">模型接口地址<input required type="url" className="mt-2 w-full rounded border p-3" placeholder="https://接口地址/v1" value={form.base_url} onChange={e => field('base_url', e.target.value)} /></label>
      <label className="block">API 密钥<input required={!id} type="password" autoComplete="off" className="mt-2 w-full rounded border p-3" placeholder={id ? '留空保留原密钥' : '输入密钥'} value={form.api_key} onChange={e => field('api_key', e.target.value)} /></label>
      <label className="block">模型名称<input required className="mt-2 w-full rounded border p-3" value={form.model_name} onChange={e => field('model_name', e.target.value)} /></label>
      <label className="block">本地转录模型<select className="ml-4 rounded border p-2" value={form.whisper_model_size} onChange={e => field('whisper_model_size', e.target.value)}>{['tiny', 'base', 'small', 'medium', 'large-v3', 'large-v3-turbo'].map(m => <option key={m}>{m}</option>)}</select></label>
      <label className="block">转录设备<select className="ml-4 rounded border p-2" value={form.device} onChange={e => field('device', e.target.value)}><option value="cpu">CPU</option><option value="cuda">NVIDIA GPU（需要 CUDA 运行库）</option></select></label>
      <p className="text-sm text-neutral-500">只有无字幕任务才会加载转录模型，首次使用会下载模型。</p>
<label className="block">转录领域词表（合计最多 200 字符）<textarea className="mt-2 w-full rounded border p-3" rows={3} value={terms} onChange={e=>setTerms(e.target.value)} /><span>用顿号分隔；只提示识别，不自动改写原文。</span></label>
      <label className="block">B 站 Cookie（可选）<textarea rows={3} className="mt-2 w-full rounded border p-3" value={form.cookie} onChange={e => field('cookie', e.target.value)} /></label>
      <p className="text-sm text-neutral-500">配置保存在本机。音频本地转录；文字总结发送到你指定的模型接口。</p>
      <button disabled={!ready || busy} className="rounded bg-neutral-900 px-5 py-3 text-white disabled:opacity-50">{busy ? '保存中…' : '保存'}</button>
      <p role="status">{message}</p>
    </form>
  </main>
}
