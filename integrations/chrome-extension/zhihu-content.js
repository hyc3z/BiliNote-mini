(() => {
  if (window.__bilinoteZhihuLoaded) return
  window.__bilinoteZhihuLoaded = true

  let lastTarget = null
  let lastPoint = { x: 0, y: 0 }
  let requestToken = 0
  let activeBubble = null
  const resultCache = new Map()

  document.addEventListener(
    'contextmenu',
    (event) => {
      lastTarget = event.target
      lastPoint = { x: event.clientX, y: event.clientY }
    },
    true,
  )

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== 'zhihu-menu') return
    void handleMenu(message.mode).catch((error) => {
      showBubble({ kind: 'error', message: String(error?.message || error) })
    })
    sendResponse({ ok: true })
  })

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

  function cleanText(value) {
    return String(value || '')
      .replace(/\u200b/g, '')
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .replace(/阅读全文|收起|展开全部/g, '')
      .trim()
  }

  function readQuestion() {
    const title =
      document.querySelector('.QuestionHeader-title')?.innerText ||
      document.querySelector('h1')?.innerText ||
      document.title.replace(/\s*-\s*知乎.*$/, '')
    const detail =
      document.querySelector('.QuestionRichText')?.innerText ||
      document.querySelector('.QuestionHeader-detail')?.innerText ||
      ''
    return { title: cleanText(title), detail: cleanText(detail).slice(0, 3000) }
  }

  function findAnswerContainer(target) {
    let node = target
    while (node && node !== document.body) {
      if (node.matches?.('.AnswerItem, .List-item, .ContentItem, article')) return node
      node = node.parentElement
    }
    const rich = target?.closest?.('.RichText')
    return (
      rich?.closest('.AnswerItem, .List-item, .ContentItem, article') ||
      rich?.parentElement ||
      null
    )
  }

  async function extractAnswer(target) {
    const item = findAnswerContainer(target)
    if (!item) return null
    const expanders = [...item.querySelectorAll('button, a')].filter((el) =>
      /阅读全文|展开全部|展开/.test(el.textContent || ''),
    )
    if (expanders.length) {
      expanders.slice(0, 2).forEach((el) => {
        try {
          el.click()
        } catch {
          // ignore
        }
      })
      await sleep(260)
    }
    const rich = item.querySelector('.RichText') || item
    const text = cleanText(rich.innerText)
    const author = cleanText(item.querySelector('.AuthorInfo-name')?.innerText || '')
    const voteup = cleanText(item.querySelector('.VoteButton--up')?.innerText || '')
    return { text: text.slice(0, 12000), author, voteup }
  }

  async function handleMenu(requestedMode) {
    const token = ++requestToken
    const question = readQuestion()
    const selection = cleanText(window.getSelection()?.toString() || '')
    const answerTarget = findAnswerContainer(lastTarget)
    const questionTarget = lastTarget?.closest?.(
      '.QuestionHeader, .QuestionHeader-title, .QuestionRichText, .QuestionHeader-detail, .QuestionHeader-main',
    )

    let mode = requestedMode
    if (mode === 'auto' || !['selection', 'answer', 'question'].includes(mode)) {
      if (selection) mode = 'selection'
      else if (answerTarget) mode = 'answer'
      else if (questionTarget) mode = 'question'
      else {
        showBubble({ kind: 'error', message: '请在回答正文或问题标题上右键。' })
        return
      }
    }

    const payload = {
      mode,
      question: question.title,
      question_detail: question.detail,
      url: location.href,
      selection: '',
      answer: '',
      context: '',
      author: '',
      voteup: '',
    }

    if (mode === 'selection') {
      if (!selection) {
        showBubble({ kind: 'error', message: '没有选中文字，请先选中一句或一段再右键。' })
        return
      }
      const answer = await extractAnswer(lastTarget)
      payload.selection = selection.slice(0, 4000)
      payload.answer = answer?.text || ''
      payload.context = (answer?.text || '').slice(0, 3000)
      payload.author = answer?.author || ''
      payload.voteup = answer?.voteup || ''
    } else if (mode === 'answer') {
      const answer = await extractAnswer(lastTarget)
      if (!answer?.text) {
        showBubble({ kind: 'error', message: '没有找到回答内容，请在一条回答的正文上右键。' })
        return
      }
      payload.answer = answer.text
      payload.author = answer.author
      payload.voteup = answer.voteup
    }

    const cacheKey = `${mode}|${payload.question}|${(payload.selection || payload.answer || payload.question).slice(0, 2000)}`
    const bubble = showBubble({ kind: 'loading' })
    if (resultCache.has(cacheKey)) {
      if (token === requestToken) bubble.render({ kind: 'result', mode, data: resultCache.get(cacheKey) })
      return
    }

    const result = await requestJudge(payload)
    if (token !== requestToken) return
    if (!result?.ok) {
      bubble.render({ kind: 'error', message: result?.error || '判断失败，请稍后重试。' })
      return
    }
    const data = result.result || {}
    if (resultCache.size > 50) resultCache.clear()
    resultCache.set(cacheKey, data)
    bubble.render({ kind: 'result', mode, data })
  }

  function requestJudge(payload) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: 'zhihu-judge', payload }, (response) => {
          if (chrome.runtime.lastError) {
            resolve({ ok: false, error: chrome.runtime.lastError.message })
            return
          }
          resolve(response || { ok: false, error: '没有收到判断结果' })
        })
      } catch (error) {
        resolve({ ok: false, error: String(error?.message || error) })
      }
    })
  }

  function showBubble({ kind, message = '' }) {
    if (activeBubble) {
      activeBubble.close()
      activeBubble = null
    }

    const host = document.createElement('div')
    host.style.cssText =
      'position:fixed;z-index:2147483647;left:0;top:0;width:0;height:0;'
    const shadow = host.attachShadow({ mode: 'open' })
    const wrap = document.createElement('div')
    wrap.className = 'bn-wrap'
    wrap.innerHTML = `
      <style>
        :host { all: initial; }
        .bn-wrap{position:absolute;display:flex;flex-direction:column;width:352px;max-width:calc(100vw - 24px);max-height:72vh;overflow:hidden;background:#fff;color:#1f2329;border:1px solid #e5e7eb;border-radius:12px;box-shadow:0 12px 36px rgba(15,23,42,.18);font:13px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}
        .bn-head{display:flex;align-items:center;justify-content:space-between;flex-shrink:0;padding:10px 12px;border-bottom:1px solid #f0f1f3;background:#fafbfc;color:#6b7280;font-size:11px;cursor:move;user-select:none;touch-action:none}
        .bn-head b{color:#111827;font-size:12px;font-weight:650}
        .bn-close{border:0;background:transparent;color:#9ca3af;font-size:15px;line-height:1;cursor:pointer;padding:2px 4px}
        .bn-body{flex:1 1 auto;min-height:0;overflow:auto;padding:12px 14px 13px}
        .bn-summary{margin:0 0 9px;color:#111827;font-size:13px;line-height:1.7}
        .bn-pill{display:inline-flex;align-items:center;gap:6px;margin-bottom:9px;padding:3px 9px;border-radius:99px;background:#eef2ff;color:#4f46e5;font-size:11px;font-weight:650}
        .bn-pill.good{background:#e8f7ee;color:#15803d}
        .bn-pill.neutral{background:#eef2f7;color:#475569}
        .bn-pill.warn{background:#fff4e5;color:#b45309}
        .bn-pill.bad{background:#fdecef;color:#b42318}
        .bn-section-label{margin:10px 0 5px;color:#9ca3af;font-size:10px;letter-spacing:.06em;text-transform:uppercase}
        .bn-list{margin:0;padding-left:18px;color:#374151;font-size:12.5px;line-height:1.7}
        .bn-list li{margin:3px 0}
        .bn-verify{margin:9px 0 0;padding:8px 10px;border-radius:8px;background:#fff8ed;color:#92400e;font-size:11.5px;line-height:1.7}
        .bn-verify strong{display:block;margin-bottom:3px;font-size:11px}
        .bn-rewrite{margin:9px 0 0;padding:8px 10px;border-radius:8px;background:#f5f7ff;color:#4338ca;font-size:11.5px;line-height:1.7}
        .bn-loading{display:flex;align-items:center;gap:9px;color:#6b7280;font-size:12px;padding:6px 0}
        .bn-spin{width:13px;height:13px;border:2px solid #dbeafe;border-top-color:#4f46e5;border-radius:50%;animation:bnspin .8s linear infinite}
        @keyframes bnspin{to{transform:rotate(360deg)}}
        .bn-error{color:#b42318;font-size:12px;line-height:1.7}
        .bn-foot{margin-top:10px;padding-top:8px;border-top:1px solid #f0f1f3;color:#9ca3af;font-size:10px}
      </style>
      <div class="bn-head"><b>BiliNote · 知乎判断</b><button class="bn-close" type="button" aria-label="关闭">×</button></div>
      <div class="bn-body"></div>
    `
    shadow.appendChild(wrap)
    document.documentElement.appendChild(host)

    const body = wrap.querySelector('.bn-body')
    const head = wrap.querySelector('.bn-head')
    let userMoved = false
    let cleanup = () => {}
    let closed = false
    const close = () => {
      if (closed) return
      closed = true
      host.remove()
      cleanup()
      if (activeBubble?.host === host) activeBubble = null
    }
    wrap.querySelector('.bn-close').addEventListener('click', close)

    const place = (x, y) => {
      const rect = wrap.getBoundingClientRect()
      const margin = 10
      const gap = 10
      let left = x + gap
      if (left + rect.width > window.innerWidth - margin) left = x - rect.width - gap
      left = Math.max(margin, Math.min(left, window.innerWidth - rect.width - margin))
      let top = y + gap
      if (top + rect.height > window.innerHeight - margin) top = y - rect.height - gap
      top = Math.max(margin, Math.min(top, window.innerHeight - rect.height - margin))
      wrap.style.left = `${left}px`
      wrap.style.top = `${top}px`
    }

    let drag = null
    head.addEventListener('pointerdown', (event) => {
      if (event.target.closest('.bn-close')) return
      const rect = wrap.getBoundingClientRect()
      drag = {
        id: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        left: rect.left,
        top: rect.top,
      }
      userMoved = true
      try {
        head.setPointerCapture(event.pointerId)
      } catch {
        // synthetic/edge-case pointer events may not support capture
      }
      wrap.style.cursor = 'grabbing'
      event.preventDefault()
    })
    head.addEventListener('pointermove', (event) => {
      if (!drag || event.pointerId !== drag.id) return
      const width = wrap.offsetWidth
      const height = wrap.offsetHeight
      const left = Math.max(
        8,
        Math.min(drag.left + event.clientX - drag.startX, window.innerWidth - width - 8),
      )
      const top = Math.max(
        8,
        Math.min(drag.top + event.clientY - drag.startY, window.innerHeight - height - 8),
      )
      wrap.style.left = `${left}px`
      wrap.style.top = `${top}px`
    })
    const endDrag = (event) => {
      if (!drag || event.pointerId !== drag.id) return
      drag = null
      wrap.style.cursor = ''
      try {
        head.releasePointerCapture(event.pointerId)
      } catch {
        // ignore
      }
    }
    head.addEventListener('pointerup', endDrag)
    head.addEventListener('pointercancel', endDrag)

    const onKey = (event) => {
      if (event.key === 'Escape') close()
    }
    cleanup = () => {
      document.removeEventListener('keydown', onKey, true)
    }
    document.addEventListener('keydown', onKey, true)

    if (kind === 'loading') {
      body.innerHTML = '<div class="bn-loading"><span class="bn-spin"></span><span>正在判断…</span></div>'
    } else if (kind === 'error') {
      body.innerHTML = '<div class="bn-error"></div>'
      body.querySelector('.bn-error').textContent = message
    }
    place(lastPoint.x, lastPoint.y)

    let api
    const render = (next) => {
      if (next.kind === 'error') {
        body.innerHTML = '<div class="bn-error"></div>'
        body.querySelector('.bn-error').textContent = next.message || '判断失败'
        if (!userMoved) requestAnimationFrame(() => place(lastPoint.x, lastPoint.y))
        return
      }
      const data = next.data || {}
      const isQuestion = next.mode === 'question'
      const verdict = String(isQuestion ? data.question_verdict || data.verdict : data.verdict || '无法判断')
      const verdictClass = verdictClassOf(verdict)
      body.innerHTML = `
        <p class="bn-summary"></p>
        <span class="bn-pill ${verdictClass}"></span>
        <div class="bn-sections"></div>
        <div class="bn-verify" hidden><strong>需要核实</strong><ul class="bn-list bn-verify-list"></ul></div>
        <div class="bn-rewrite" hidden></div>
        <div class="bn-foot">AI 判断 · 仅供参考${data.model ? ' · ' + escapeHtml(data.model) : ''}</div>
      `
      body.querySelector('.bn-summary').textContent = data.summary || '未能生成摘要'
      body.querySelector('.bn-pill').textContent = verdict

      const sectionHost = body.querySelector('.bn-sections')
      const sections = [
        ['可取之处', data.strengths],
        ['不足之处', data.weaknesses],
        ['值得思考点', data.thoughts],
      ]
      let renderedSections = 0
      for (const [label, items] of sections) {
        if (!Array.isArray(items) || !items.length) continue
        const heading = document.createElement('div')
        heading.className = 'bn-section-label'
        heading.textContent = label
        const list = document.createElement('ul')
        list.className = 'bn-list'
        for (const item of items) {
          const li = document.createElement('li')
          li.textContent = item
          list.appendChild(li)
        }
        sectionHost.append(heading, list)
        renderedSections++
      }
      if (!renderedSections) {
        const heading = document.createElement('div')
        heading.className = 'bn-section-label'
        heading.textContent = '值得思考点'
        const list = document.createElement('ul')
        list.className = 'bn-list'
        for (const item of data.reasons || []) {
          const li = document.createElement('li')
          li.textContent = item
          list.appendChild(li)
        }
        sectionHost.append(heading, list)
      }

      const verifyBox = body.querySelector('.bn-verify')
      const verifyList = body.querySelector('.bn-verify-list')
      for (const item of data.verify || []) {
        const li = document.createElement('li')
        li.textContent = item
        verifyList.appendChild(li)
        verifyBox.hidden = false
      }
      if (isQuestion && data.rewrite) {
        const rewrite = body.querySelector('.bn-rewrite')
        rewrite.hidden = false
        rewrite.textContent = '改写建议：' + data.rewrite
      }
      if (!userMoved) requestAnimationFrame(() => place(lastPoint.x, lastPoint.y))
    }

    api = { host, close, render }
    activeBubble = api
    return api
  }

  function verdictClassOf(value) {
    if (/较可靠|基本合理/.test(value)) return 'good'
    if (/存疑|有预设|前提需核实/.test(value)) return 'warn'
    if (/无法判断|一般/.test(value)) return 'neutral'
    return 'warn'
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    })[char])
  }
})()
