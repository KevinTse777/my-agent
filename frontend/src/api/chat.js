import { request } from './client'

const CHAT_ENDPOINT = import.meta.env.VITE_CHAT_ENDPOINT || '/chat/agent'

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
