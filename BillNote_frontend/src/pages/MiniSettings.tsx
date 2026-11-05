import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import request from '@/utils/request'
import { addModel, addProvider, updateProviderById } from '@/services/model'

export default function MiniSettings() {
  const [form, setForm] = useState({ base_url: '', api_key: '', model_name: '', cookie: '', whisper_model_size: 'small', device: 'cpu' })
  const [id, setId] = useState('')
  const [terms,setTerms]=useState('')
  const [tagName,setTagName]=useState('数码')
  const [tagLists,setTagLists]=useState<Record<string,string[]>>({})
  useEffect(()=>{request.get('/tag_terms').then((data:any)=>{setTagLists(data.tags);setTerms((data.tags['数码']||[]).join('、'))}).catch(()=>setMessage('标签词表读取失败，请重启后端后重试'))},[])
  async function saveTag(){try{const data:any=await request.post('/tag_terms',{tag:tagName,terms:terms.split(/[、,，\n]+/).map(t=>t.trim()).filter(Boolean)});setTagLists(data.tags);setMessage('标签词表已保存；仅用于绑定此标签的视频后续转录。')}catch(e:any){setMessage(e?.detail||e?.msg||'词表保存失败')}}

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
<section className="tag-dictionary"><h2>标签与领域词表</h2><p>按内容类型维护词表。旧词表已保留为“数码”，不会自动用于所有视频。</p><label>选择标签 <select value={tagName} onChange={e=>{setTagName(e.target.value);setTerms((tagLists[e.target.value]||[]).join('、'))}}>{Array.from(new Set([...Object.keys(tagLists),tagName])).map(t=><option key={t}>{t}</option>)}</select></label><label>新建标签名称<input maxLength={30} value={tagName} onChange={e=>{setTagName(e.target.value);setTerms((tagLists[e.target.value]||[]).join('、'))}}/></label><label>专有名词（最多 200 字符）<textarea rows={3} value={terms} onChange={e=>setTerms(e.target.value)}/></label><p>用顿号或逗号分隔；视频可绑定多个标签。只提示识别，不自动改写已保存的原文。</p><button type="button" onClick={saveTag}>保存此标签词表</button></section>
      <div className="cookie-field"><div className="cookie-field-heading"><label htmlFor="bilibili-cookie">B 站 Cookie（可选）</label><details className="cookie-help" onKeyDown={e=>{if(e.key==='Escape'){e.currentTarget.removeAttribute('open');(e.currentTarget.querySelector('summary') as HTMLElement)?.blur()}}}><summary aria-label="如何获取 B 站 Cookie" aria-describedby="cookie-help-text">?</summary><div id="cookie-help-text" role="tooltip" className="cookie-tip"><strong>如何获取 B 站 Cookie</strong><ol><li>在浏览器打开 B 站并登录。</li><li>按 F12，切换到「网络 / Network」，然后刷新页面。</li><li>选择一个发往 api.bilibili.com 的请求。</li><li>打开「标头 / Headers → 请求标头 / Request Headers」，找到 Cookie。</li><li>复制完整内容，不包含 Cookie: 字样，粘贴到下方并点击「保存」。</li></ol><p>找不到时，确认查看的是请求标头，而不是响应标头的 Set-Cookie。</p><p>浏览器登录状态不会自动共享给本工具。Cookie 过期后需重新获取。</p><p className="cookie-tip-note">Cookie 相当于登录凭证：仅保存到本地设置，不要发送给他人或截图分享。</p></div></details></div><textarea id="bilibili-cookie" rows={3} autoComplete="off" spellCheck={false} className="mt-2 w-full rounded border p-3" value={form.cookie} onChange={e => field('cookie', e.target.value)} /></div>
      <p className="text-sm text-neutral-500">配置保存在本机。音频本地转录；文字总结发送到你指定的模型接口。</p>
      <button disabled={!ready || busy} className="rounded bg-neutral-900 px-5 py-3 text-white disabled:opacity-50">{busy ? '保存中…' : '保存'}</button>
      <p role="status">{message}</p>
    </form>
  </main>
}
