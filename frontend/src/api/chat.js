import { buildApiUrl, request } from './client'

const CHAT_ENDPOINT = import.meta.env.VITE_CHAT_ENDPOINT || '/chat/agent'
const SESSION_CHAT_ENDPOINT = '/chat/agent/session'
const SESSION_CHAT_STREAM_ENDPOINT = '/chat/agent/session/stream'
const STREAM_TIMEOUT = Number(import.meta.env.VITE_API_TIMEOUT || 60000)

function pickData(payload) {
  if (payload && typeof payload === 'object' && payload.data && typeof payload.data === 'object') {
    return payload.data
  }
  return payload || {}
}

function normalizeSources(data) {
  const raw = Array.isArray(data?.sources) ? data.sources : []
  const normalized = []

  for (const item of raw) {
    const title = typeof item?.title === 'string' ? item.title.trim() : ''
    const url = typeof item?.url === 'string' ? item.url.trim() : ''
    const snippet = typeof item?.snippet === 'string' ? item.snippet.trim() : ''

    if (!url) {
      continue
    }

    normalized.push({
      title: title || url,
      url,
      snippet,
    })
  }

  return normalized
}

export async function sendChatMessage(message) {
  const payload = await request(CHAT_ENDPOINT, {
    method: 'POST',
    body: { message },
  })

  const data = pickData(payload)

  return {
    answer: typeof data.answer === 'string' ? data.answer : '',
    toolsUsed: Array.isArray(data.tools_used) ? data.tools_used : [],
    sources: normalizeSources(data),
    requestId: data.request_id || payload?.request_id || null,
  }
}

export async function sendSessionChatMessage(sessionId, message) {
  const payload = await request(SESSION_CHAT_ENDPOINT, {
    method: 'POST',
    body: {
      session_id: sessionId,
      message,
    },
  })

  const data = pickData(payload)

  return {
    sessionId: data.session_id || sessionId,
    answer: typeof data.answer === 'string' ? data.answer : '',
    toolsUsed: Array.isArray(data.tools_used) ? data.tools_used : [],
    sources: normalizeSources(data),
    requestId: data.request_id || payload?.request_id || null,
  }
}

function extractTextError(payload, fallback) {
  if (!payload) {
    return fallback
  }
  if (typeof payload === 'string') {
    return payload || fallback
  }
  return payload.message || payload.detail || fallback
}

function parseLineEvent(line) {
  try {
    return JSON.parse(line)
  } catch {
    return null
  }
}

export async function sendSessionChatMessageStream(sessionId, message, handlers = {}, options = {}) {
  const requestController = new AbortController()
  let abortedByUser = false
  let abortedByTimeout = false
  let externalAbortHandler = null
  const externalSignal = options?.signal
  const timeoutMs = Number(options?.timeoutMs || STREAM_TIMEOUT)
  const timeoutId = window.setTimeout(() => {
    abortedByTimeout = true
    requestController.abort()
  }, timeoutMs)

  if (externalSignal) {
    externalAbortHandler = () => {
      abortedByUser = true
      requestController.abort()
    }
    if (externalSignal.aborted) {
      externalAbortHandler()
    } else {
      externalSignal.addEventListener('abort', externalAbortHandler, { once: true })
    }
  }

  let requestId = null
  let answer = ''
  let toolsUsed = []
  let sources = []

  try {
    const response = await fetch(buildApiUrl(SESSION_CHAT_STREAM_ENDPOINT), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        session_id: sessionId,
        message,
      }),
      signal: requestController.signal,
    })

    if (!response.ok) {
      const text = await response.text()
      throw new Error(extractTextError(text, `请求失败（HTTP ${response.status}）`))
    }

    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('流式响应不可用')
    }

    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        break
      }

      buffer += decoder.decode(value, { stream: true })
      let index = buffer.indexOf('\n')
      while (index >= 0) {
        const line = buffer.slice(0, index).trim()
        buffer = buffer.slice(index + 1)
        index = buffer.indexOf('\n')

        if (!line) {
          continue
        }

        const event = parseLineEvent(line)
        if (!event || typeof event !== 'object') {
          continue
        }

        if (event.request_id && !requestId) {
          requestId = event.request_id
        }

        if (event.type === 'token') {
          const token = typeof event.content === 'string' ? event.content : ''
          if (token) {
            answer += token
            handlers.onToken?.(token, event)
          }
          continue
        }

        if (event.type === 'tool') {
          const toolName = typeof event.name === 'string' ? event.name : ''
          if (toolName && !toolsUsed.includes(toolName)) {
            toolsUsed.push(toolName)
            handlers.onTool?.(toolName, event)
          }
          continue
        }

        if (event.type === 'sources') {
          const sourceList = normalizeSources({ sources: event.sources })
          if (sourceList.length) {
            const map = new Map(sources.map((item) => [item.url, item]))
            for (const source of sourceList) {
              map.set(source.url, source)
            }
            sources = Array.from(map.values())
            handlers.onSources?.(sources, event)
          }
          continue
        }

        if (event.type === 'end') {
          if (typeof event.answer === 'string' && !answer) {
            answer = event.answer
          }
          if (Array.isArray(event.tools_used) && event.tools_used.length) {
            toolsUsed = event.tools_used
          }
          if (Array.isArray(event.sources)) {
            sources = normalizeSources({ sources: event.sources })
          }
          handlers.onEnd?.(event)
          continue
        }

        if (event.type === 'error') {
          const messageText = typeof event.message === 'string' ? event.message : '流式请求失败'
          handlers.onError?.(messageText, event)
          throw new Error(messageText)
        }
      }
    }

    const tail = buffer.trim()
    if (tail) {
      const event = parseLineEvent(tail)
      if (event?.type === 'error') {
        const messageText = typeof event.message === 'string' ? event.message : '流式请求失败'
        handlers.onError?.(messageText, event)
        throw new Error(messageText)
      }
    }

    return {
      sessionId,
      answer: answer || '助手未返回文本内容',
      toolsUsed,
      sources,
      requestId,
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      if (abortedByUser) {
        throw new Error('请求已取消')
      }
      if (abortedByTimeout) {
        throw new Error('请求超时，请稍后重试')
      }
      throw new Error('请求超时，请稍后重试')
    }
    throw error
  } finally {
    window.clearTimeout(timeoutId)
    if (externalSignal && externalAbortHandler) {
      externalSignal.removeEventListener('abort', externalAbortHandler)
    }
  }
}
