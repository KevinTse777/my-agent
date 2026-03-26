const STORAGE_KEY = 'my-agent-chat-sessions-v1'
const MAX_SESSIONS = 40

function safeJsonParse(raw) {
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function trimText(value, maxLength = 36) {
  if (typeof value !== 'string') {
    return '新会话'
  }
  const text = value.trim()
  if (!text) {
    return '新会话'
  }
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text
}

export function createSessionId() {
  const rand = Math.random().toString(36).slice(2, 8)
  return `sess_${Date.now()}_${rand}`
}

export function createSessionDraft() {
  const now = new Date().toISOString()
  return {
    id: createSessionId(),
    title: '新会话',
    createdAt: now,
    updatedAt: now,
    messages: [
      {
        id: 1,
        role: 'assistant',
        content: '你好，我是你的学习助手。当前会话会保留上下文记忆。',
        toolsUsed: [],
        sources: [],
      },
    ],
  }
}

export function sanitizeSessions(input) {
  if (!Array.isArray(input)) {
    return []
  }

  return input
    .filter((session) => session && typeof session.id === 'string')
    .map((session) => {
      const messages = Array.isArray(session.messages) ? session.messages : []
      return {
        id: session.id,
        title: trimText(session.title),
        createdAt: typeof session.createdAt === 'string' ? session.createdAt : new Date().toISOString(),
        updatedAt: typeof session.updatedAt === 'string' ? session.updatedAt : new Date().toISOString(),
        messages: messages.map((msg, index) => ({
          id: typeof msg?.id === 'number' ? msg.id : index + 1,
          role: msg?.role === 'user' ? 'user' : 'assistant',
          content: typeof msg?.content === 'string' ? msg.content : '',
          toolsUsed: Array.isArray(msg?.toolsUsed) ? msg.toolsUsed : [],
          sources: Array.isArray(msg?.sources) ? msg.sources : [],
        })),
      }
    })
    .sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1))
    .slice(0, MAX_SESSIONS)
}

export function loadSessions() {
  if (typeof window === 'undefined') {
    return []
  }
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) {
    return []
  }
  return sanitizeSessions(safeJsonParse(raw))
}

export function saveSessions(sessions) {
  if (typeof window === 'undefined') {
    return
  }
  const clean = sanitizeSessions(sessions)
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(clean))
}

export function makeSessionTitleFromMessage(message) {
  return trimText(message, 22)
}
