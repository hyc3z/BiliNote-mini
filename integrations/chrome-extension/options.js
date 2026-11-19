import { trimBase } from './common.js'

const refs = {
  form: document.getElementById('form'),
  apiBase: document.getElementById('apiBase'),
  workbenchBase: document.getElementById('workbenchBase'),
  modelKey: document.getElementById('modelKey'),
  notify: document.getElementById('notify'),
  reloadModels: document.getElementById('reloadModels'),
  test: document.getElementById('test'),
  openSettings: document.getElementById('openSettings'),
  result: document.getElementById('result'),
  health: document.getElementById('health'),
}

const send = (message) =>
  chrome.runtime.sendMessage(message).catch((error) => ({
    ok: false,
    error: String(error?.message || error),
  }))

function setResult(text, isError) {
  refs.result.textContent = text
  refs.result.classList.toggle('error', !!isError)
}

function setHealth(ok, text) {
  refs.health.className = 'pill ' + (ok ? 'online' : 'offline')
  refs.health.textContent = text
}

function fillModels(models, currentKey) {
  const options = [new Option('自动选择第一个已启用模型', '')]
  for (const model of models || []) {
    const key = `${model.provider_id}:${model.model_name}`
    options.push(new Option(`${model.model_name}（provider ${model.provider_id}）`, key))
  }
  refs.modelKey.replaceChildren(...options)
  refs.modelKey.value = options.some((option) => option.value === currentKey) ? currentKey : ''
}

async function load() {
  const data = await send({ type: 'state' })
  if (!data?.ok) {
    setHealth(false, '扩展后台未响应')
    setResult('读取设置失败，请重新加载扩展。', true)
    return
  }
  const settings = data.settings || {}
  refs.apiBase.value = settings.apiBase || ''
  refs.workbenchBase.value = settings.workbenchBase || ''
  refs.notify.checked = settings.notify !== false
  fillModels(data.models, settings.modelKey || '')

  const health = await send({ type: 'test' })
  if (health?.ok) setHealth(true, '后端已连接')
  else setHealth(false, health?.message || '后端未连接')
}

async function reloadModels() {
  const data = await send({ type: 'models' })
  if (!data?.ok) {
    setResult(data?.error || '读取模型列表失败', true)
    return
  }
  fillModels(data.models, refs.modelKey.value)
  setResult('模型列表已刷新')
}

refs.form.addEventListener('submit', async (event) => {
  event.preventDefault()
  const apiBase = trimBase(refs.apiBase.value)
  const workbenchBase = trimBase(refs.workbenchBase.value)
  for (const [name, value] of [
    ['后端接口地址', apiBase],
    ['工作台地址', workbenchBase],
  ]) {
    try {
      new URL(value)
    } catch {
      setResult(`${name}不是合法的 URL。`, true)
      return
    }
  }
  const data = await send({
    type: 'save-settings',
    settings: {
      apiBase,
      workbenchBase,
      modelKey: refs.modelKey.value,
      notify: refs.notify.checked,
    },
  })
  if (!data?.ok) {
    setResult(data?.error || '保存失败', true)
    return
  }
  setResult('已保存')
})

refs.reloadModels.addEventListener('click', () => {
  void reloadModels()
})

refs.test.addEventListener('click', async () => {
  const data = await send({ type: 'test' })
  if (data?.ok) {
    setHealth(true, '后端已连接')
    setResult('连接成功')
    await reloadModels()
  } else {
    setHealth(false, '后端未连接')
    setResult(data?.message || '连接失败', true)
  }
})

refs.openSettings.addEventListener('click', () => {
  void send({ type: 'open-settings' })
})

void load()
