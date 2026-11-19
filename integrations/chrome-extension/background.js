// BiliNote 省流 —— MV3 service worker
// 右键视频页 -> POST /api/generate_note -> 轮询 /api/task_status -> 徽标进度 + 通知。
import {
  ACCOUNT_PROVIDERS,
  canonicalVideoUrl,
  isFinal,
  providerForUrl,
  stageLabel,
  trimBase,
  readSettings,
  writeSettings,
  readTasks,
  writeTasks,
  resolveWorkbenchBase,
  workbenchUrlWithBase,
  settingsUrl,
} from './common.js'

const POLL_ALARM = 'bilinote-poll'
const MENU_ITEM = 'bilinote-summarize'
const SYNC_ITEM_PREFIX = 'bilinote-sync-'
const ZHIHU_MENU_ITEM = 'zhihu-judge'
const ZHIHU_PAGES = ['*://*.zhihu.com/question/*', '*://zhihu.com/question/*']
// 改协议时递增；popup 用它检测“弹窗是新代码、后台还是旧 service worker”的错位。
const PROTOCOL = 3
const BADGE_COLOR = '#6d4aff'
const DONE_COLOR = '#1f9d55'
const FAILED_COLOR = '#d64545'
const SUPPORTED_PAGES = [
  // 在支持的站点上显示菜单；提交前由 canonicalVideoUrl 收敛为单个视频。
  '*://*.bilibili.com/*',
  '*://bilibili.com/*',
  '*://*.b23.tv/*',
  '*://b23.tv/*',
  '*://*.youtube.com/*',
  '*://youtube.com/*',
  '*://youtu.be/*',
  '*://*.instagram.com/*',
  '*://instagram.com/*',
]

const SYNC_MENU_PAGES = [
  '*://*.youtube.com/*',
  '*://youtube.com/*',
  '*://youtu.be/*',
  '*://*.bilibili.com/*',
  '*://bilibili.com/*',
  '*://*.b23.tv/*',
  '*://b23.tv/*',
  'http://127.0.0.1/*',
  'http://localhost/*',
]

const ACTION_ICONS = {
  default: {
    16: 'icons/16.png',
    32: 'icons/32.png',
    48: 'icons/48.png',
    128: 'icons/128.png',
  },
  youtube: {
    16: 'icons/youtube/16.png',
    32: 'icons/youtube/32.png',
    48: 'icons/youtube/48.png',
    128: 'icons/youtube/128.png',
  },
  bilibili: {
    16: 'icons/bilibili/16.png',
    32: 'icons/bilibili/32.png',
    48: 'icons/bilibili/48.png',
    128: 'icons/bilibili/128.png',
  },
  zhihu: {
    16: 'icons/zhihu/16.png',
    32: 'icons/zhihu/32.png',
    48: 'icons/zhihu/48.png',
    128: 'icons/zhihu/128.png',
  },
}

let pollPromise = null
let pumpTimer = null

// ---------------------------------------------------------------- 生命周期

chrome.runtime.onInstalled.addListener(() => {
  createMenus()
  void updateActionIcon()
  void pollActive()
  void refreshBadge()
})

chrome.runtime.onStartup.addListener(() => {
  createMenus()
  void updateActionIcon()
  void pollActive()
})

chrome.tabs.onActivated.addListener(() => {
  void updateActionIcon()
})

chrome.tabs.onUpdated.addListener((_tabId, changeInfo, tab) => {
  if ((changeInfo.url || changeInfo.status === 'complete') && tab?.active) {
    void updateActionIcon()
  }
})

chrome.windows.onFocusChanged.addListener(() => {
  void updateActionIcon()
})

chrome.contextMenus.onClicked.addListener((info, tab) => {
  void handleMenuClick(info, tab)
})

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === POLL_ALARM) void pollActive()
})

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  handleMessage(message).then(sendResponse, (error) =>
    sendResponse({ ok: false, error: String(error?.message || error) }),
  )
  return true
})

chrome.notifications.onClicked.addListener((id) => {
  void handleNotificationClick(id)
})

chrome.notifications.onButtonClicked.addListener((id) => {
  void handleNotificationClick(id)
})

// 每次 service worker 被唤醒时补一次轮询；不会被重复注册。
void pollActive()
void updateActionIcon()

// ---------------------------------------------------------------- 页面图标

function pageKind(value) {
  try {
    const url = new URL(value)
    const host = url.hostname.toLowerCase()
    // 工作台（127.0.0.1 / localhost）沿用 BiliNote 默认图标。
    if (host === '127.0.0.1' || host === 'localhost') return 'default'
    const provider = providerForUrl(value)
    if (provider?.id === 'youtube' || provider?.id === 'bilibili' || provider?.id === 'zhihu') {
      return provider.id
    }
  } catch {
    // ignore
  }
  return 'default'
}

async function updateActionIcon() {
  let kind = 'default'
  try {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true })
    kind = pageKind(tab?.url || '')
  } catch {
    // 没有活动窗口时保持默认图标。
  }
  try {
    await chrome.action.setIcon({ path: ACTION_ICONS[kind] || ACTION_ICONS.default })
  } catch {
    // 图标文件缺失时不影响其它功能。
  }
}

// ---------------------------------------------------------------- 右键菜单

function createMenus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_ITEM,
      title: '省流不看',
      contexts: ['page', 'video', 'link'],
      documentUrlPatterns: SUPPORTED_PAGES,
    })
    for (const provider of Object.values(ACCOUNT_PROVIDERS)) {
      if (!provider.cookieUrls.length) continue
      chrome.contextMenus.create({
        id: `${SYNC_ITEM_PREFIX}${provider.id}`,
        title: `同步 ${provider.label} 登录`,
        contexts: ['page'],
        documentUrlPatterns: provider.menuPages || SYNC_MENU_PAGES,
      })
    }
    chrome.contextMenus.create({
      id: ZHIHU_MENU_ITEM,
      title: 'BiliNote 判断',
      contexts: ['page', 'selection', 'link', 'image'],
      documentUrlPatterns: ZHIHU_PAGES,
    })
  })
}

async function handleMenuClick(info, tab) {
  if (typeof info.menuItemId === 'string' && info.menuItemId.startsWith(SYNC_ITEM_PREFIX)) {
    const providerId = info.menuItemId.slice(SYNC_ITEM_PREFIX.length)
    await handleSyncMenu(providerId)
    return
  }
  if (info.menuItemId === ZHIHU_MENU_ITEM) {
    if (!tab?.id) return
    try {
      await chrome.tabs.sendMessage(tab.id, { type: 'zhihu-menu', mode: 'auto' })
    } catch {
      try {
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ['zhihu-content.js'],
        })
        await chrome.tabs.sendMessage(tab.id, { type: 'zhihu-menu', mode: 'auto' })
      } catch {
        await notifyProblem('知乎页面脚本暂时不可用，请刷新知乎页面后再试。', 'tip')
      }
    }
    return
  }
  if (info.menuItemId !== MENU_ITEM) return
  const url = videoUrlFrom(info, tab)
  if (!url) {
    await notifyProblem('没有识别到视频链接。请在 B 站 / YouTube / Instagram 视频页或视频链接上右键。', 'tip')
    return
  }
  const result = await startTask(url, tab?.title || '')
  if (result.ok) {
    if (!result.duplicate) await notifyStarted(result.task)
    return
  }
  if (result.openSettings) {
    await notifyProblem(result.error, 'settings')
    await showAttention('!')
    return
  }
  await notifyProblem(result.error, 'tip')
  await showAttention('!')
}

async function showAttention(text) {
  await chrome.action.setBadgeText({ text })
  await chrome.action.setBadgeBackgroundColor({ color: FAILED_COLOR })
  await chrome.action.setTitle({ title: 'BiliNote 省流 · 点击查看原因' })
}

// 在 YouTube / B 站 / 工作台右键同步对应平台登录；只显示“已更新”，不展示账号名。
async function handleSyncMenu(providerId) {
  const provider = ACCOUNT_PROVIDERS[providerId]
  if (!provider) return
  const result = await syncAccount(providerId)
  if (!result.ok) {
    await notifyProblem(result.error, 'tip')
    return
  }
  if (result.status?.error) {
    await notifyProblem(`Cookie 已更新，但暂时无法验证：${result.status.error}`, 'tip')
    return
  }
  await createNotification(`bilinote-sync-${Date.now()}`, {
    title: `${provider.label} Cookie 已更新`,
    message: '已从当前 Chrome 同步到 BiliNote 后端，本地保存。',
    contextMessage: 'BiliNote',
  })
}

// ---------------------------------------------------------------- 视频地址识别

function videoUrlFrom(info, tab) {
  // 在链接上右键时只认这个链接，避免误把当前页视频再提交一遍。
  const candidates = info.linkUrl ? [info.linkUrl] : [tab?.url, info.frameUrl]
  for (const value of candidates) {
    if (value && isVideoUrl(value)) return value
  }
  return ''
}

function isVideoUrl(value) {
  try {
    const url = new URL(value)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return false
    const host = url.hostname.toLowerCase()
    if (host === 'b23.tv' || host.endsWith('.b23.tv')) return url.pathname.length > 1
    if (host === 'bilibili.com' || host.endsWith('.bilibili.com')) {
      return /^\/video\/[^/]+/.test(url.pathname)
    }
    if (host === 'youtu.be') return url.pathname.length > 1
    if (host === 'youtube.com' || host.endsWith('.youtube.com') || host === 'youtube-nocookie.com') {
      return url.pathname === '/watch' || /^\/(shorts|live|embed)\//.test(url.pathname)
    }
    if (host === 'instagram.com' || host.endsWith('.instagram.com')) {
      return /^\/(p|reel|reels|tv)\//.test(url.pathname)
    }
    return false
  } catch {
    return false
  }
}

function platformOf(value) {
  try {
    const host = new URL(value).hostname.toLowerCase()
    if (host.includes('youtube') || host === 'youtu.be') return 'youtube'
    if (host.includes('instagram')) return 'instagram'
    return 'bilibili'
  } catch {
    return 'bilibili'
  }
}

// ---------------------------------------------------------------- 开始任务

async function startTask(rawUrl, title) {
  const settings = await readSettings()
  // 只提交单个视频：B 站保留 BV/p，YouTube 去掉 list/index 等播放列表参数。
  const videoUrl = canonicalVideoUrl(String(rawUrl || '').trim())
  if (!isVideoUrl(videoUrl)) {
    return { ok: false, error: '没有识别到 B 站 / YouTube / Instagram 视频链接。' }
  }

  let models
  try {
    models = await fetchModels(settings)
  } catch {
    return {
      ok: false,
      error: `连不上 BiliNote 后端（${trimBase(settings.apiBase)}）。请先运行 start-mini.ps1，或到扩展设置里修改接口地址。`,
    }
  }
  if (!models.length) {
    return {
      ok: false,
      error: '还没有启用总结模型。请先在工作台的“模型与设置”里添加并启用一个文字模型，再回来右键。',
      openSettings: true,
    }
  }

  const selected =
    models.find((m) => `${m.provider_id}:${m.model_name}` === settings.modelKey) || models[0]

  const tasks = await readTasks()
  const running = Object.values(tasks).find(
    (task) => task && task.url === videoUrl && !isFinal(task.status),
  )
  if (running) {
    return { ok: true, taskId: running.id, duplicate: true, task: running }
  }

  const payload = {
    video_url: videoUrl,
    platform: platformOf(videoUrl),
    quality: 'medium',
    model_name: selected.model_name,
    provider_id: String(selected.provider_id),
    format: ['link'],
    link: true,
    style: 'minimal',
    grid_size: [],
  }

  let result
  try {
    result = await apiFetch('/api/generate_note', {
      method: 'POST',
      body: payload,
      timeout: 30000,
      settings,
    })
  } catch (error) {
    return { ok: false, error: `提交失败：${error?.message || error}` }
  }
  if (!result || result.code !== 0) {
    return { ok: false, error: errorMessage(result) || '提交失败，后端没有返回任务编号。' }
  }
  const taskId = result.data?.task_id
  if (!taskId) return { ok: false, error: '提交失败：后端没有返回任务编号。' }

  const task = {
    id: taskId,
    url: videoUrl,
    title: String(title || '').trim().slice(0, 200),
    platform: payload.platform,
    status: 'PENDING',
    message: '已提交，等待后端处理',
    percent: null,
    progress: {},
    createdAt: Date.now(),
    updatedAt: Date.now(),
    notified: false,
  }
  tasks[taskId] = task
  pruneTasks(tasks)
  await writeTasks(tasks)
  await refreshBadge(tasks)
  await ensureAlarm(tasks)
  startPump()
  return { ok: true, taskId, task, settings }
}

// ---------------------------------------------------------------- 轮询与徽标

function pollActive() {
  if (!pollPromise) {
    pollPromise = pollActiveInner().finally(() => {
      pollPromise = null
    })
  }
  return pollPromise
}

async function pollActiveInner() {
  const settings = await readSettings()
  const tasks = await readTasks()
  const active = Object.values(tasks).filter((task) => task && !isFinal(task.status))

  for (const task of active) {
    try {
      const payload = await apiFetch(
        `/api/task_status/${encodeURIComponent(task.id)}?include_transcript=false`,
        { timeout: 12000, settings },
      )
      if (!payload || payload.code !== 0) {
        task.message = errorMessage(payload) || '读取进度失败'
        continue
      }
      const data = payload.data || {}
      const status = data.status || task.status
      task.status = status
      task.message = data.message || ''
      task.percent =
        typeof data.progress?.percent === 'number' ? data.progress.percent : null
      task.progress = {
        elapsed_seconds: data.progress?.elapsed_seconds,
        completed_chunks: data.progress?.completed_chunks,
        total_chunks: data.progress?.total_chunks,
      }
      task.updatedAt = Date.now()
      if (isFinal(status)) {
        task.finishedAt = Date.now()
        if (!task.notified) {
          task.notified = true
          if (status === 'SUCCESS') await notifySuccess(task, settings)
          if (status === 'FAILED') await notifyFailure(task, settings)
        }
      }
    } catch {
      task.message = task.message || '后端暂时不可达，稍后自动重试'
    }
  }

  pruneTasks(tasks)
  await writeTasks(tasks)
  await refreshBadge(tasks)
  await ensureAlarm(tasks)
  if (Object.values(tasks).some((task) => task && !isFinal(task.status))) startPump()
  return tasks
}

// 2 秒软轮询：MV3 的 SW 会被休眠，所以同时用 alarms 兜底；SW 醒着时就近似实时。
function startPump() {
  if (pumpTimer !== null) return
  pumpTimer = setTimeout(async () => {
    pumpTimer = null
    const tasks = await readTasks()
    if (!Object.values(tasks).some((task) => task && !isFinal(task.status))) return
    await pollActive()
    startPump()
  }, 1500)
}

function stopPump() {
  if (pumpTimer !== null) {
    clearTimeout(pumpTimer)
    pumpTimer = null
  }
}

// 只保留进行中的任务 + 最近 20 条已结束记录，避免 storage 无限增长。
function pruneTasks(tasks) {
  const finished = Object.values(tasks)
    .filter((task) => task && isFinal(task.status))
    .sort((a, b) => (b.finishedAt || b.updatedAt || 0) - (a.finishedAt || a.updatedAt || 0))
  for (const task of finished.slice(20)) delete tasks[task.id]
}

async function ensureAlarm(tasks) {
  const active = Object.values(tasks).some((task) => task && !isFinal(task.status))
  if (!active) {
    await chrome.alarms.clear(POLL_ALARM)
    stopPump()
    return
  }
  const existing = await chrome.alarms.get(POLL_ALARM)
  if (!existing) chrome.alarms.create(POLL_ALARM, { periodInMinutes: 0.5 })
}

async function refreshBadge(knownTasks) {
  const tasks = knownTasks || (await readTasks())
  const list = Object.values(tasks).filter(Boolean)
  const active = list.filter((task) => !isFinal(task.status))

  if (active.length) {
    let text
    if (active.length === 1) {
      const task = active[0]
      // 工具栏不能画真正的进度条，用百分比徽标近似 Chrome 下载提示。
      text =
        typeof task.percent === 'number'
          ? String(Math.max(0, Math.min(100, Math.round(task.percent))))
          : '…'
    } else {
      text = String(active.length)
    }
    const detail = active
      .map(
        (task) =>
          `${stageLabel(task.status)}${typeof task.percent === 'number' ? ' ' + Math.round(task.percent) + '%' : ''}`,
      )
      .join(' · ')
    await chrome.action.setBadgeText({ text })
    await chrome.action.setBadgeBackgroundColor({ color: BADGE_COLOR })
    await chrome.action.setTitle({
      title: `BiliNote 省流 · ${detail}\n点击查看任务列表`,
    })
    return
  }

  const recent = list
    .filter(
      (task) => isFinal(task.status) && Date.now() - (task.finishedAt || task.updatedAt || 0) < 15000,
    )
    .sort((a, b) => (b.finishedAt || 0) - (a.finishedAt || 0))[0]

  if (recent) {
    const success = recent.status === 'SUCCESS'
    await chrome.action.setBadgeText({ text: success ? '✓' : '!' })
    await chrome.action.setBadgeBackgroundColor({
      color: success ? DONE_COLOR : FAILED_COLOR,
    })
    await chrome.action.setTitle({
      title: success ? '省流完成，点击查看报告' : '省流失败，点击查看原因',
    })
    return
  }

  await chrome.action.setBadgeText({ text: '' })
  await chrome.action.setTitle({ title: 'BiliNote 省流' })
}

// ---------------------------------------------------------------- 通知

async function notifySuccess(task, settings) {
  if (settings.notify === false) return
  await createNotification(`bilinote-${task.id}`, {
    title: '省流完成',
    message: task.title || '笔记已生成，点击查看报告。',
    contextMessage: '点击打开报告',
    buttons: [{ title: '打开报告' }],
  })
}

async function notifyFailure(task, settings) {
  if (settings.notify === false) return
  await createNotification(`bilinote-${task.id}`, {
    title: '省流失败',
    message: task.message || '处理失败，可在工作台重试。',
    contextMessage: '点击查看详情',
    buttons: [{ title: '打开工作台' }],
  })
}

async function notifyStarted(task) {
  const settings = await readSettings()
  if (settings.notify === false) return
  await createNotification(`bilinote-started-${task.id}`, {
    title: '已开始省流',
    message: task.title || task.url,
    contextMessage: '生成期间可以继续浏览',
  })
}

async function notifyProblem(message, kind) {
  const settings = await readSettings()
  if (settings.notify === false) return
  const id = kind === 'settings' ? 'bilinote-settings' : `bilinote-problem-${Date.now()}`
  await createNotification(id, {
    title: kind === 'settings' ? '还没有启用总结模型' : 'BiliNote 省流',
    message,
    contextMessage: kind === 'settings' ? '点击打开设置' : 'BiliNote',
    buttons: kind === 'settings' ? [{ title: '打开设置' }] : [],
  })
}

async function createNotification(id, options) {
  try {
    await chrome.notifications.create(id, {
      type: 'basic',
      iconUrl: chrome.runtime.getURL('icons/128.png'),
      priority: 1,
      ...options,
    })
  } catch {
    // 用户可能关闭了系统通知，忽略即可。
  }
}

async function handleNotificationClick(id) {
  if (id === 'bilinote-settings') {
    await openSettingsPage()
    return
  }
  const match = id.match(/^bilinote-(?:started-)?([0-9a-fA-F-]{36})$/)
  if (match) {
    await openTask(match[1])
    return
  }
  await openWorkbenchPage()
}

// ---------------------------------------------------------------- 打开页面

async function openTask(taskId) {
  const [tasks, settings] = await Promise.all([readTasks(), readSettings()])
  const task = tasks[taskId]
  if (!task) {
    await openWorkbenchPage()
    return
  }
  const base = await resolveWorkbenchBase(settings)
  await chrome.tabs.create({ url: workbenchUrlWithBase(base, task) })
}

async function openWorkbenchPage() {
  const settings = await readSettings()
  const base = await resolveWorkbenchBase(settings)
  await chrome.tabs.create({ url: workbenchUrlWithBase(base) })
}

async function openSettingsPage() {
  const settings = await readSettings()
  await chrome.tabs.create({ url: settingsUrl(settings) })
}

// ---------------------------------------------------------------- 平台登录同步

// 从 Chrome 的 Cookie 库里读出指定平台的 Cookie，拼成后端需要的请求头格式。
// 只在 service worker 内使用，不写进 extension storage，也不回传给 popup。
async function collectProviderCookie(provider) {
  const lists = await Promise.all(
    provider.cookieUrls.map((url) => chrome.cookies.getAll({ url })),
  )
  const values = new Map()
  for (const cookie of lists.flat()) {
    const domain = String(cookie.domain || '').toLowerCase().replace(/^\./, '')
    if (!provider.hosts.some((item) => domain === item || domain.endsWith(`.${item}`))) continue
    if (!values.has(cookie.name)) values.set(cookie.name, cookie.value)
  }
  return {
    header: [...values].map(([name, value]) => `${name}=${value}`).join('; '),
    hasAuth: provider.authCookies.some((name) => values.has(name)),
    count: values.size,
  }
}

async function fetchAccountStatus(provider, settings) {
  try {
    const payload = await apiFetch(provider.statusPath, { timeout: 10000, settings })
    if (payload?.code === 0) return payload.data || { configured: true, isLogin: false }
    return {
      configured: true,
      isLogin: false,
      error: errorMessage(payload) || `读取 ${provider.label} 登录状态失败`,
    }
  } catch (error) {
    const message = String(error?.message || error)
    if (/404|not\s*found/i.test(message)) {
      return {
        configured: true,
        isLogin: false,
        error: '后端接口不存在（HTTP 404）。请重启 start-mini.ps1 后再试。',
      }
    }
    return { configured: true, isLogin: false, error: `后端未连接：${message}` }
  }
}

async function syncAccount(providerId) {
  const provider = ACCOUNT_PROVIDERS[providerId]
  if (!provider) return { ok: false, error: `不支持的平台：${providerId}` }
  const settings = await readSettings()
  let collected
  try {
    collected = await collectProviderCookie(provider)
  } catch (error) {
    return { ok: false, error: `读取 Chrome 的 ${provider.label} Cookie 失败：${error?.message || error}` }
  }
  if (!collected.hasAuth) {
    return {
      ok: false,
      error: `当前 Chrome 没有登录 ${provider.label}（找不到 ${provider.authCookies.join(' / ')}）。请先在 ${provider.hosts[0]} 登录，再同步。`,
    }
  }
  let saved
  try {
    saved = await apiFetch('/api/update_downloader_cookie', {
      method: 'POST',
      body: { platform: provider.id, cookie: collected.header },
      timeout: 15000,
      settings,
    })
  } catch (error) {
    return { ok: false, error: `写入后端失败：${error?.message || error}` }
  }
  if (!saved || saved.code !== 0) {
    return { ok: false, error: errorMessage(saved) || '后端拒绝了 Cookie，请确认后端已启动。' }
  }
  return { ok: true, status: await fetchAccountStatus(provider, settings), count: collected.count }
}

// ---------------------------------------------------------------- 知乎单条判断

let zhihuModelCache = null
let zhihuModelCacheAt = 0

async function zhihuModels(settings) {
  if (zhihuModelCache && Date.now() - zhihuModelCacheAt < 60000) return zhihuModelCache
  const models = await fetchModels(settings)
  zhihuModelCache = models
  zhihuModelCacheAt = Date.now()
  return models
}

async function pickZhihuModel(settings) {
  const models = await zhihuModels(settings)
  if (!models.length) throw new Error('还没有启用文字模型，请先在工作台设置中添加模型')
  const flash = models.find((model) => /flash/i.test(String(model.model_name || '')))
  if (flash) return flash
  const selected = models.find(
    (model) => `${model.provider_id}:${model.model_name}` === settings.modelKey,
  )
  return selected || models[0]
}

async function judgeZhihu(payload) {
  const settings = await readSettings()
  let model
  try {
    model = await pickZhihuModel(settings)
  } catch (error) {
    return { ok: false, error: String(error?.message || error) }
  }
  try {
    const response = await apiFetch('/api/zhihu/judge', {
      method: 'POST',
      body: {
        ...payload,
        model_name: model.model_name,
        provider_id: String(model.provider_id),
      },
      timeout: 60000,
      settings,
    })
    if (!response || response.code !== 0) {
      return { ok: false, error: errorMessage(response) || '判断失败，请稍后重试' }
    }
    return { ok: true, result: response.data }
  } catch (error) {
    const message = String(error?.message || error)
    if (/404|not\s*found/i.test(message)) {
      return { ok: false, error: '后端还没有知乎判断接口，请重启 start-mini.ps1 后再试。' }
    }
    return { ok: false, error: `判断失败：${message}` }
  }
}

// ---------------------------------------------------------------- 扩展列表摘要/移除

async function taskSummary(taskId) {
  const tasks = await readTasks()
  const task = tasks[taskId]
  if (!task) return { ok: false, error: '任务不存在' }
  if (task.status !== 'SUCCESS') return { ok: false, error: '任务还没有完成' }
  if (typeof task.summary === 'string') {
    return { ok: true, summary: task.summary, title: task.title || '' }
  }
  const settings = await readSettings()
  try {
    const response = await apiFetch(`/api/task_summary/${encodeURIComponent(taskId)}`, {
      timeout: 10000,
      settings,
    })
    if (!response || response.code !== 0) {
      return { ok: false, error: errorMessage(response) || '读取省流失败' }
    }
    const latest = await readTasks()
    if (!latest[taskId]) return { ok: false, error: '任务已从扩展列表移除' }
    latest[taskId].summary = String(response.data?.summary || '')
    latest[taskId].updatedAt = Date.now()
    await writeTasks(latest)
    return { ok: true, summary: latest[taskId].summary, title: response.data?.title || latest[taskId].title || '' }
  } catch (error) {
    const message = String(error?.message || error)
    if (/404|not\s*found/i.test(message)) {
      return { ok: false, error: '后端还没有摘要接口，请重启 start-mini.ps1 后再试' }
    }
    return { ok: false, error: `读取省流失败：${message}` }
  }
}

async function dismissTask(taskId) {
  const tasks = await readTasks()
  if (!tasks[taskId]) return { ok: true }
  delete tasks[taskId]
  await writeTasks(tasks)
  await refreshBadge(tasks)
  return { ok: true }
}

// ---------------------------------------------------------------- 后端调用

async function apiFetch(path, { method = 'GET', body, timeout = 20000, settings } = {}) {
  const config = settings || (await readSettings())
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const response = await fetch(trimBase(config.apiBase) + path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
      cache: 'no-store',
    })
    const text = await response.text()
    let payload = null
    try {
      payload = text ? JSON.parse(text) : null
    } catch {
      throw new Error(`后端返回了无法解析的内容（HTTP ${response.status}）`)
    }
    if (!response.ok) {
      if (payload && typeof payload.code === 'number') return payload
      throw new Error(errorMessage(payload) || `HTTP ${response.status}`)
    }
    return payload
  } finally {
    clearTimeout(timer)
  }
}

async function fetchModels(settings) {
  const payload = await apiFetch('/api/model_list', { timeout: 10000, settings })
  if (!payload || payload.code !== 0) {
    throw new Error(errorMessage(payload) || '读取模型列表失败，请检查后端')
  }
  return Array.isArray(payload.data) ? payload.data : []
}

function errorMessage(payload) {
  if (!payload) return ''
  if (typeof payload.msg === 'string' && payload.msg) return payload.msg
  if (Array.isArray(payload.detail)) {
    return payload.detail
      .map((item) => item?.msg || (typeof item === 'string' ? item : JSON.stringify(item)))
      .join('；')
  }
  if (typeof payload.detail === 'string') return payload.detail
  return ''
}

// ---------------------------------------------------------------- 消息

async function handleMessage(message) {
  switch (message?.type) {
    case 'ping':
      return {
        ok: true,
        protocol: PROTOCOL,
        version: chrome.runtime.getManifest().version,
      }
    case 'state': {
      const [settings, tasks] = await Promise.all([readSettings(), readTasks()])
      let models = []
      try {
        models = await fetchModels(settings)
      } catch {
        // 后端离线时保持 popup 可用，由调用方展示离线状态。
      }
      return { ok: true, settings, tasks, models }
    }
    case 'poll': {
      let tasks
      try {
        tasks = await pollActive()
      } catch {
        tasks = await readTasks()
      }
      return { ok: true, settings: await readSettings(), tasks }
    }
    case 'start':
      return startTask(message.url, message.title)
    case 'open-task':
      await openTask(message.taskId)
      return { ok: true }
    case 'open-workbench':
      await openWorkbenchPage()
      return { ok: true }
    case 'open-settings':
      await openSettingsPage()
      return { ok: true }
    case 'open-options':
      chrome.runtime.openOptionsPage()
      return { ok: true }
    case 'open-extensions':
      try {
        await chrome.tabs.create({ url: `chrome://extensions/?id=${chrome.runtime.id}` })
        return { ok: true }
      } catch (error) {
        return { ok: false, error: String(error?.message || error) }
      }
    case 'models':
      return { ok: true, models: await fetchModels(await readSettings()) }
    case 'account-status': {
      const provider = ACCOUNT_PROVIDERS[message.provider] || ACCOUNT_PROVIDERS.bilibili
      return { ok: true, status: await fetchAccountStatus(provider, await readSettings()) }
    }
    case 'account-sync':
      return syncAccount(message.provider || 'bilibili')
    case 'zhihu-judge':
      return judgeZhihu(message.payload || {})
    case 'task-summary':
      return taskSummary(message.taskId)
    case 'dismiss-task':
      return dismissTask(message.taskId)
    // 兼容 0.3.x 的旧 popup（协议不匹配时会提示重载，这里只是兜底）。
    case 'bili-status':
      return { ok: true, status: await fetchAccountStatus(ACCOUNT_PROVIDERS.bilibili, await readSettings()) }
    case 'sync-bili-cookie':
      return syncAccount('bilibili')
    case 'save-settings': {
      const settings = await writeSettings(message.settings || {})
      await refreshBadge()
      return { ok: true, settings }
    }
    case 'test': {
      try {
        const payload = await apiFetch('/api/sys_check', { timeout: 5000 })
        if (payload?.code === 0) return { ok: true, message: '连接成功' }
        return { ok: false, message: errorMessage(payload) || '后端返回异常' }
      } catch (error) {
        return { ok: false, message: `无法连接：${error?.message || error}` }
      }
    }
    default:
      return { ok: false, error: `未知消息：${message?.type}` }
  }
}
