import {
  ACCOUNT_PROVIDERS,
  providerForUrl,
  isFinal,
  stageLabel,
  formatElapsed,
} from './common.js'

// 与 background.js 的 PROTOCOL 保持一致；不一致说明 service worker 还是旧代码。
const PROTOCOL = 3
let protocolOk = true

const refs = {
  status: document.getElementById('status'),
  version: document.getElementById('version'),
  notice: document.getElementById('notice'),
  reloadWarning: document.getElementById('reload-warning'),
  reloadExtension: document.getElementById('reload-extension'),
  openExtensions: document.getElementById('open-extensions'),
  accountLabel: document.getElementById('account-label'),
  biliStatus: document.getElementById('bili-status'),
  syncCookie: document.getElementById('sync-cookie'),
  accountMessage: document.getElementById('account-message'),
  activeSection: document.getElementById('active-section'),
  activeList: document.getElementById('active-list'),
  activeCount: document.getElementById('active-count'),
  recentSection: document.getElementById('recent-section'),
  recentList: document.getElementById('recent-list'),
  empty: document.getElementById('empty'),
  refresh: document.getElementById('refresh'),
  openWorkbench: document.getElementById('open-workbench'),
  openOptions: document.getElementById('open-options'),
  reloadFooter: document.getElementById('reload-footer'),
}

const state = {
  tasks: {},
  offline: false,
  provider: ACCOUNT_PROVIDERS.bilibili,
}

const summaryRequests = new Set()
const summaryTried = new Set()

const send = (message) =>
  chrome.runtime.sendMessage(message).catch((error) => ({
    ok: false,
    error: String(error?.message || error),
  }))

function timeText(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' })
}

function requestTaskSummary(task) {
  if (typeof task.summary === 'string' || summaryRequests.has(task.id) || summaryTried.has(task.id)) {
    return
  }
  summaryRequests.add(task.id)
  void send({ type: 'task-summary', taskId: task.id }).then((res) => {
    summaryRequests.delete(task.id)
    summaryTried.add(task.id)
    if (!state.tasks[task.id]) return
    const current = state.tasks[task.id]
    if (res?.ok) {
      state.tasks[task.id] = { ...current, summary: res.summary || '', summaryError: '' }
    } else {
      state.tasks[task.id] = {
        ...current,
        summary: '',
        summaryError: res?.error || '读取省流失败',
      }
    }
    render()
  })
}

function dismissTask(task) {
  void send({ type: 'dismiss-task', taskId: task.id }).then(() => {
    delete state.tasks[task.id]
    summaryTried.delete(task.id)
    render()
  })
}

function makeTaskCard(task) {
  const final = isFinal(task.status)
  const success = task.status === 'SUCCESS'
  const card = document.createElement('div')
  card.className = 'task'
  card.tabIndex = 0
  card.setAttribute('role', 'button')
  card.title = '打开报告 / 查看进度'

  const open = () => {
    void send({ type: 'open-task', taskId: task.id })
    window.close()
  }
  card.addEventListener('click', (event) => {
    if (event.target.closest('.task-dismiss')) return
    open()
  })
  card.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      open()
    }
  })

  const top = document.createElement('span')
  top.className = 'task-top'

  const title = document.createElement('span')
  title.className = 'task-title'
  title.textContent = task.title || task.url || task.id

  const badge = document.createElement('span')
  badge.className =
    'badge ' + (final ? String(task.status).toLowerCase() : 'active')
  badge.textContent = stageLabel(task.status)
  top.append(title, badge)

  if (final) {
    const dismiss = document.createElement('button')
    dismiss.type = 'button'
    dismiss.className = 'task-dismiss'
    dismiss.textContent = '×'
    dismiss.title = '从扩展列表移除'
    dismiss.setAttribute('aria-label', '从扩展列表移除')
    dismiss.addEventListener('click', (event) => {
      event.stopPropagation()
      event.preventDefault()
      dismissTask(task)
    })
    top.append(dismiss)
  }

  card.append(top)

  if (success) {
    const summary = document.createElement('span')
    summary.className = 'task-summary'
    const label = document.createElement('b')
    label.textContent = '省流：'
    const text = document.createElement('span')
    if (typeof task.summary === 'string') {
      text.textContent = task.summary || task.summaryError || '暂无省流，点击查看报告'
    } else {
      text.textContent = '正在读取省流…'
      requestTaskSummary(task)
    }
    summary.append(label, text)
    card.append(summary)

    const foot = document.createElement('span')
    foot.className = 'task-foot'
    const meta = document.createElement('span')
    meta.className = 'meta'
    meta.textContent = timeText(task.finishedAt || task.updatedAt)
    const openHint = document.createElement('span')
    openHint.className = 'task-open'
    openHint.textContent = '查看完整报告 →'
    foot.append(meta, openHint)
    card.append(foot)
    return card
  }

  if (final) {
    const sub = document.createElement('span')
    sub.className = 'task-sub'
    sub.textContent = task.message || '可在工作台重试'
    const foot = document.createElement('span')
    foot.className = 'task-foot'
    const meta = document.createElement('span')
    meta.className = 'meta'
    meta.textContent = timeText(task.finishedAt || task.updatedAt)
    foot.append(meta)
    card.append(sub, foot)
    return card
  }

  const sub = document.createElement('span')
  sub.className = 'task-sub active'
  // 徽标已经显示阶段，正文优先展示后端给的细节（如“正在总结第 3/12 段”）。
  sub.textContent = task.message || stageLabel(task.status)

  const meter = document.createElement('span')
  meter.className = 'meter'
  const fill = document.createElement('span')
  fill.className = 'meter-fill'
  const percent =
    typeof task.percent === 'number' ? Math.max(0, Math.min(100, task.percent)) : null
  if (percent === null) meter.classList.add('indeterminate')
  else fill.style.width = percent + '%'
  meter.append(fill)

  const foot = document.createElement('span')
  foot.className = 'task-foot'
  const meta = document.createElement('span')
  meta.className = 'meta'
  const elapsed = task.progress?.elapsed_seconds
  meta.textContent = elapsed ? '已用时 ' + formatElapsed(elapsed) : '刚提交'
  const pct = document.createElement('span')
  pct.className = 'percent'
  pct.textContent = percent === null ? '' : Math.round(percent) + '%'
  foot.append(meta, pct)

  card.append(sub, meter, foot)
  return card
}

function render() {
  const tasks = Object.values(state.tasks || {}).filter(Boolean)
  const active = tasks
    .filter((task) => !isFinal(task.status))
    .sort((a, b) => (a.createdAt || 0) - (b.createdAt || 0))
  const recent = tasks
    .filter((task) => isFinal(task.status))
    .sort(
      (a, b) => (b.finishedAt || b.updatedAt || 0) - (a.finishedAt || a.updatedAt || 0),
    )
    .slice(0, 8)

  refs.status.textContent = state.offline
    ? '本地后端未连接'
    : active.length
      ? `${active.length} 个任务处理中`
      : '就绪'
  refs.notice.hidden = !state.offline
  if (state.offline) {
    refs.notice.textContent = '连不上本地 BiliNote 后端，请确认 start-mini.ps1 已运行；接口地址可在“扩展设置”里修改。'
  }

  refs.activeList.replaceChildren(...active.map(makeTaskCard))
  refs.recentList.replaceChildren(...recent.map(makeTaskCard))
  refs.activeSection.hidden = active.length === 0
  refs.recentSection.hidden = recent.length === 0
  refs.activeCount.textContent = active.length ? String(active.length) : ''
  refs.empty.hidden = active.length + recent.length > 0
}

async function refresh(mode = {}) {
  const requests = [send({ type: mode.poll ? 'poll' : 'state' })]
  if (mode.test) requests.push(send({ type: 'test' }))
  const [data, health] = await Promise.all(requests)
  if (data?.ok) {
    const incoming = data.tasks || {}
    // 轮询可能早于摘要写回；保留当前弹窗已经拿到的摘要，避免卡片闪回“正在读取”。
    for (const task of Object.values(incoming)) {
      const previous = state.tasks[task.id]
      if (previous && typeof previous.summary === 'string' && typeof task.summary !== 'string') {
        task.summary = previous.summary
      }
    }
    state.tasks = incoming
    // 只有主动健康检查才能确认“后端在线”，轮询成功不代表后端在线（SW 本身总是响应）。
    if (health) state.offline = health.ok !== true
  } else {
    state.offline = true
  }
  render()
}

async function resolveProvider() {
  try {
    const focused = await chrome.tabs.query({ active: true, lastFocusedWindow: true })
    for (const tab of focused) {
      if (tab.url && !tab.url.startsWith('chrome-extension://')) {
        const provider = providerForUrl(tab.url)
        if (provider) return provider
      }
    }
    const active = await chrome.tabs.query({ active: true })
    for (const tab of active) {
      if (tab.url && !tab.url.startsWith('chrome-extension://')) {
        const provider = providerForUrl(tab.url)
        if (provider) return provider
      }
    }
  } catch {
    // 读取活动标签失败时退回 B 站。
  }
  return ACCOUNT_PROVIDERS.bilibili
}

function accountLabel(provider) {
  return provider.loginVerified ? `${provider.label}登录` : `${provider.label} Cookie`
}

function renderAccountStatus(status) {
  const el = refs.biliStatus
  const provider = state.provider
  if (!status) {
    el.textContent = '检测中…'
    el.className = 'account-state'
    return
  }
  if (status.error) {
    el.textContent = '状态未知：' + status.error
    el.className = 'account-state warn'
    return
  }
  if (!status.configured) {
    el.textContent = provider.loginVerified ? '未登录 / 未配置' : '未同步 Cookie'
    el.className = 'account-state warn'
    return
  }
  if (!provider.loginVerified) {
    el.textContent = 'Cookie 已同步'
    el.className = 'account-state ok'
    return
  }
  if (status.isLogin) {
    el.textContent = `已登录 ${provider.label}`
    el.className = 'account-state ok'
  } else {
    el.textContent = '未登录 / Cookie 已失效'
    el.className = 'account-state warn'
  }
}

async function refreshAccountStatus() {
  if (!protocolOk || state.provider.contentOnly) return
  const res = await send({ type: 'account-status', provider: state.provider.id })
  renderAccountStatus(res?.ok ? res.status : { error: '扩展后台未响应' })
}

async function checkProtocol() {
  const res = await send({ type: 'ping' })
  const currentVersion = chrome.runtime.getManifest().version
  refs.version.textContent = 'v' + currentVersion
  const versionOk = !res?.version || res.version === currentVersion
  protocolOk = Boolean(res?.ok && res.protocol === PROTOCOL && versionOk)
  refs.reloadWarning.hidden = protocolOk
  if (!protocolOk) {
    refs.syncCookie.disabled = true
    refs.biliStatus.textContent = '需要重新加载扩展'
    refs.biliStatus.className = 'account-state warn'
  }
  return protocolOk
}

refs.reloadExtension?.addEventListener('click', () => {
  chrome.runtime.reload()
})

refs.reloadFooter?.addEventListener('click', () => {
  chrome.runtime.reload()
})

refs.openExtensions?.addEventListener('click', async () => {
  const res = await send({ type: 'open-extensions' })
  if (!res?.ok) {
    refs.reloadWarning.hidden = false
    refs.reloadWarning.querySelector('span').textContent =
      '无法打开扩展管理页，请手动打开 chrome://extensions。'
  }
})

refs.refresh.addEventListener('click', () => {
  void refresh({ poll: true, test: true })
  void refreshAccountStatus()
})

refs.syncCookie.addEventListener('click', async () => {
  if (!protocolOk) {
    refs.reloadWarning.hidden = false
    return
  }
  const provider = state.provider
  refs.syncCookie.disabled = true
  refs.syncCookie.textContent = '同步中…'
  refs.accountMessage.hidden = true
  refs.accountMessage.classList.remove('error')
  const res = await send({ type: 'account-sync', provider: provider.id })
  refs.syncCookie.disabled = false
  refs.syncCookie.textContent = '同步'
  if (res?.ok) {
    renderAccountStatus(res.status)
    if (res.status?.error) {
      refs.accountMessage.classList.add('error')
      refs.accountMessage.textContent = `Cookie 已写入后端，但暂时无法验证：${res.status.error}`
    } else if (provider.loginVerified && !res.status?.isLogin) {
      refs.accountMessage.classList.add('error')
      refs.accountMessage.textContent = `已写入 Cookie，但后端仍未登录 ${provider.label}。请确认 Chrome 里已登录后重试。`
    } else {
      refs.accountMessage.classList.remove('error')
      refs.accountMessage.textContent = `已从 Chrome 更新 ${provider.label} Cookie`
    }
    refs.accountMessage.hidden = false
  } else {
    refs.accountMessage.textContent = res?.error || '同步失败'
    refs.accountMessage.classList.add('error')
    refs.accountMessage.hidden = false
  }
})

refs.openWorkbench.addEventListener('click', () => {
  void send({ type: 'open-workbench' })
  window.close()
})

refs.openOptions.addEventListener('click', () => {
  void send({ type: 'open-options' })
  window.close()
})

void refresh({ test: true })
void (async () => {
  state.provider = await resolveProvider()
  const ok = await checkProtocol()
  if (state.provider.contentOnly) {
    refs.accountLabel.textContent = '知乎判断'
    refs.biliStatus.textContent = '右键回答 / 选中文字'
    refs.biliStatus.className = 'account-state'
    refs.syncCookie.hidden = true
    refs.accountMessage.hidden = true
    return
  }
  refs.accountLabel.textContent = accountLabel(state.provider)
  if (ok) await refreshAccountStatus()
})()
setInterval(() => {
  void refresh({ poll: true })
}, 1500)
