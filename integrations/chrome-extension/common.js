// 共享常量与小工具：service worker、popup、options 都会用到。

export const DEFAULT_SETTINGS = {
  apiBase: 'http://127.0.0.1:8483',
  workbenchBase: 'http://127.0.0.1:8483',
  modelKey: '',
  notify: true,
}

export const STAGE_LABELS = {
  PENDING: '排队中',
  PARSING: '读取字幕',
  DOWNLOADING: '读取媒体',
  MODEL_DOWNLOADING: '下载转录模型',
  MODEL_LOADING: '加载转录模型',
  TRANSCRIBING: '音频转录',
  SUMMARIZING: '总结观点',
  SAVING: '保存笔记',
  RUNNING: '处理中',
  SUCCESS: '已完成',
  FAILED: '失败',
  CANCELLED: '已停止',
  CANCELLING: '停止中',
}

export const FINAL_STATUSES = new Set(['SUCCESS', 'FAILED', 'CANCELLED'])

// 平台登录/Cookie 同步的注册表。以后接知乎，在这里加一条 + 后端实现即可。
export const ACCOUNT_PROVIDERS = {
  bilibili: {
    id: 'bilibili',
    label: 'B 站',
    hosts: ['bilibili.com', 'b23.tv'],
    cookieUrls: ['https://www.bilibili.com/', 'https://api.bilibili.com/'],
    authCookies: ['SESSDATA'],
    statusPath: '/api/account_status?platform=bilibili',
    loginVerified: true,
    menuPages: [
      '*://*.bilibili.com/*',
      '*://bilibili.com/*',
      '*://*.b23.tv/*',
      '*://b23.tv/*',
      'http://127.0.0.1/*',
      'http://localhost/*',
    ],
  },
  youtube: {
    id: 'youtube',
    label: 'YouTube',
    hosts: ['youtube.com', 'youtu.be', 'youtube-nocookie.com'],
    cookieUrls: ['https://www.youtube.com/'],
    authCookies: ['SID', 'SAPISID', 'LOGIN_INFO', '__Secure-3PSID'],
    statusPath: '/api/account_status?platform=youtube',
    loginVerified: false,
    menuPages: [
      '*://*.youtube.com/*',
      '*://youtube.com/*',
      '*://youtu.be/*',
      'http://127.0.0.1/*',
      'http://localhost/*',
    ],
  },
  zhihu: {
    id: 'zhihu',
    label: '知乎',
    hosts: ['zhihu.com'],
    cookieUrls: [],
    authCookies: [],
    statusPath: '',
    loginVerified: false,
    contentOnly: true,
  },
}

export function providerForUrl(value) {
  try {
    const host = new URL(String(value || '')).hostname.toLowerCase()
    return (
      Object.values(ACCOUNT_PROVIDERS).find((provider) =>
        provider.hosts.some((item) => host === item || host.endsWith(`.${item}`)),
      ) || null
    )
  } catch {
    return null
  }
}

export const isFinal = (status) => FINAL_STATUSES.has(status)

export const stageLabel = (status) => STAGE_LABELS[status] || status || '等待处理'

export function trimBase(value) {
  return String(value || '').trim().replace(/\/+$/, '')
}

export async function readSettings() {
  const stored = await chrome.storage.local.get('settings')
  return { ...DEFAULT_SETTINGS, ...(stored.settings || {}) }
}

export async function writeSettings(patch) {
  const next = { ...(await readSettings()), ...patch }
  await chrome.storage.local.set({ settings: next })
  return next
}

export async function readTasks() {
  const stored = await chrome.storage.local.get('tasks')
  return stored.tasks || {}
}

export async function writeTasks(tasks) {
  await chrome.storage.local.set({ tasks })
}

// 把点击到的链接收敛成“单个视频”地址：去掉播放列表参数，B 站只保留 BV + p。
// 这样右键合集/播放列表里的某一条时，后端永远只处理这一条。
export function canonicalVideoUrl(value) {
  try {
    const url = new URL(String(value || '').trim())
    const host = url.hostname.toLowerCase()

    if (host === 'b23.tv' || host.endsWith('.b23.tv')) return url.toString()

    if (host === 'bilibili.com' || host.endsWith('.bilibili.com')) {
      const bv = url.pathname.match(/\/video\/(BV[0-9A-Za-z]+)/)?.[1]
      if (bv) {
        const p = url.searchParams.get('p')
        return `https://www.bilibili.com/video/${bv}${p && /^\d+$/.test(p) ? `?p=${p}` : ''}`
      }
      return url.toString()
    }

    if (host === 'youtu.be') {
      const id = url.pathname.split('/').filter(Boolean)[0]
      return id ? `https://www.youtube.com/watch?v=${encodeURIComponent(id)}` : url.toString()
    }

    if (host === 'youtube.com' || host.endsWith('.youtube.com') || host === 'youtube-nocookie.com') {
      const videoId = url.searchParams.get('v')
      if (videoId) return `https://www.youtube.com/watch?v=${encodeURIComponent(videoId)}`
      const match = url.pathname.match(/^\/(shorts|live|embed)\/([^/?#]+)/)
      if (match) return `https://www.youtube.com/${match[1]}/${match[2]}`
      return url.toString()
    }

    if (host === 'instagram.com' || host.endsWith('.instagram.com')) {
      const match = url.pathname.match(/^\/(p|reel|reels|tv)\/([^/?#]+)/)
      if (match) return `https://www.instagram.com/${match[1]}/${match[2]}/`
      return url.toString()
    }

    return url.toString()
  } catch {
    return String(value || '')
  }
}

// 工作台支持 #task=<id>&url=&title=：任务没完成时会落入“处理中”，完成后直接打开报告。
// 用 hash 而不是 query，避免 Vite dev server 对 query 里的 https%3A%2F%2F... 做路径校验而 403。
export function workbenchUrl(settings, task) {
  const base = trimBase(settings.workbenchBase) || DEFAULT_SETTINGS.workbenchBase
  return workbenchUrlWithBase(base, task)
}

export function workbenchUrlWithBase(base, task) {
  const url = new URL(trimBase(base) + '/')
  if (task) {
    const params = new URLSearchParams()
    params.set('task', task.id)
    if (task.url) params.set('url', task.url)
    if (task.title) params.set('title', String(task.title).slice(0, 120))
    url.hash = params.toString()
  }
  return url.toString()
}

export async function resolveWorkbenchBase(settings) {
  const base = trimBase(settings.workbenchBase) || DEFAULT_SETTINGS.workbenchBase
  // Installed builds serve the UI from the API port. Older settings may still
  // point at the Vite dev server; fall back to 8483 when 3015 is not running.
  if (/:(3015)(\/|$)/.test(base)) {
    try {
      await fetch(base, { method: 'HEAD', signal: AbortSignal.timeout(800) })
    } catch {
      return trimBase(settings.apiBase) || base
    }
  }
  return base
}

export function settingsUrl(settings) {
  return `${trimBase(settings.workbenchBase) || DEFAULT_SETTINGS.workbenchBase}/settings`
}

export function formatElapsed(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}
