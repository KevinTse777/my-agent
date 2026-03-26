<template>
  <div class="app-shell">
    <div class="workspace">
      <aside class="session-sidebar">
        <div class="sidebar-header">
          <h1 class="title">智能对话助手</h1>
          <button class="new-session-btn" type="button" @click="createNewSession">
            + 新会话
          </button>
        </div>

        <div class="session-list">
          <button
            v-for="session in sessions"
            :key="session.id"
            type="button"
            class="session-item"
            :class="{ active: session.id === activeSessionId }"
            @click="selectSession(session.id)"
          >
            <span class="session-title">{{ session.title }}</span>
            <span class="session-time">{{ formatDateTime(session.updatedAt) }}</span>
          </button>
        </div>

        <div class="sidebar-footer">
          <button
            class="ghost-btn"
            type="button"
            :disabled="sessions.length <= 1 || loading"
            @click="deleteCurrentSession"
          >
            删除当前会话
          </button>
        </div>
      </aside>

      <main class="chat-card">
        <header class="chat-header">
          <div>
            <h2 class="chat-title">{{ activeSession?.title || '会话' }}</h2>
            <p class="subtitle">当前会话内启用后端记忆</p>
          </div>
          <div class="status-badge">{{ loading ? '请求中' : '就绪' }}</div>
        </header>

        <MessageList :messages="activeMessages" :loading="loading" />
        <ChatInput :loading="loading" :error="errorMessage" @send="onSend" />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import MessageList from './components/MessageList.vue'
import ChatInput from './components/ChatInput.vue'
import { sendSessionChatMessage } from './api/chat'
import {
  createSessionDraft,
  loadSessions,
  makeSessionTitleFromMessage,
  saveSessions,
} from './utils/sessionStore'

const sessions = ref([])
const activeSessionId = ref('')
const loading = ref(false)
const errorMessage = ref('')

const activeSession = computed(() =>
  sessions.value.find((session) => session.id === activeSessionId.value) || null
)

const activeMessages = computed(() => activeSession.value?.messages || [])

onMounted(() => {
  const loaded = loadSessions()
  if (loaded.length) {
    sessions.value = loaded
    activeSessionId.value = loaded[0].id
    return
  }

  const initial = createSessionDraft()
  sessions.value = [initial]
  activeSessionId.value = initial.id
})

watch(
  sessions,
  (next) => {
    if (next.length) {
      saveSessions(next)
    }
  },
  { deep: true }
)

function formatDateTime(isoText) {
  if (!isoText) {
    return '--'
  }
  const date = new Date(isoText)
  if (Number.isNaN(date.getTime())) {
    return '--'
  }
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function selectSession(sessionId) {
  if (loading.value) {
    return
  }
  activeSessionId.value = sessionId
  errorMessage.value = ''
}

function createNewSession() {
  if (loading.value) {
    return
  }
  const draft = createSessionDraft()
  sessions.value = [draft, ...sessions.value]
  activeSessionId.value = draft.id
  errorMessage.value = ''
}

function deleteCurrentSession() {
  if (loading.value || sessions.value.length <= 1) {
    return
  }
  const currentId = activeSessionId.value
  const remained = sessions.value.filter((session) => session.id !== currentId)
  sessions.value = remained
  activeSessionId.value = remained[0]?.id || ''
  errorMessage.value = ''
}

function updateSession(sessionId, updater) {
  sessions.value = sessions.value.map((session) => {
    if (session.id !== sessionId) {
      return session
    }
    return updater(session)
  })
}

function bringSessionToTop(sessionId) {
  const index = sessions.value.findIndex((session) => session.id === sessionId)
  if (index <= 0) {
    return
  }
  const current = sessions.value[index]
  const rest = sessions.value.filter((session) => session.id !== sessionId)
  sessions.value = [current, ...rest]
}

async function onSend(text) {
  const trimmed = text.trim()
  const currentSession = activeSession.value
  if (!trimmed || loading.value || !currentSession) {
    return
  }

  errorMessage.value = ''
  const now = new Date().toISOString()

  updateSession(currentSession.id, (session) => {
    const nextMessages = [
      ...session.messages,
      {
        id: session.messages.length + 1,
        role: 'user',
        content: trimmed,
        toolsUsed: [],
        sources: [],
      },
    ]
    return {
      ...session,
      title: session.messages.length <= 1 ? makeSessionTitleFromMessage(trimmed) : session.title,
      updatedAt: now,
      messages: nextMessages,
    }
  })
  bringSessionToTop(currentSession.id)

  loading.value = true

  try {
    const result = await sendSessionChatMessage(currentSession.id, trimmed)
    const answerAt = new Date().toISOString()

    updateSession(currentSession.id, (session) => {
      const nextMessages = [
        ...session.messages,
        {
          id: session.messages.length + 1,
          role: 'assistant',
          content: result.answer || '助手未返回文本内容',
          toolsUsed: result.toolsUsed || [],
          sources: result.sources || [],
        },
      ]
      return {
        ...session,
        updatedAt: answerAt,
        messages: nextMessages,
      }
    })
    bringSessionToTop(currentSession.id)
  } catch (error) {
    errorMessage.value = error.message || '请求失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
  background:
    radial-gradient(1200px 420px at 50% -200px, rgba(71, 148, 208, 0.2), transparent),
    linear-gradient(180deg, #edf5fb 0%, #f4f8fc 60%, #f6f9fd 100%);
  padding: 24px 16px;
  display: flex;
  justify-content: center;
}

.workspace {
  width: min(1200px, 100%);
  height: calc(100vh - 48px);
  min-height: 620px;
  display: grid;
  grid-template-columns: 280px 1fr;
  border: 1px solid #cfdfeb;
  border-radius: 18px;
  background: #fafdff;
  box-shadow: 0 12px 35px rgba(38, 78, 110, 0.08);
  overflow: hidden;
}

.session-sidebar {
  display: flex;
  flex-direction: column;
  border-right: 1px solid #d8e5f0;
  background: linear-gradient(180deg, #f2f8fd 0%, #edf5fb 100%);
}

.sidebar-header {
  padding: 14px;
  border-bottom: 1px solid #d8e5f0;
}

.title {
  margin: 0 0 10px;
  font-size: 17px;
  letter-spacing: 0.2px;
  color: #13324a;
}

.new-session-btn {
  width: 100%;
  height: 36px;
  border-radius: 10px;
  border: 1px solid #2d7fbe;
  background: #237fc3;
  color: #f2f8ff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.new-session-btn:hover {
  background: #1b73b4;
}

.session-list {
  flex: 1;
  padding: 10px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.session-item {
  width: 100%;
  text-align: left;
  border: 1px solid #d2e2ee;
  background: #f9fcff;
  border-radius: 10px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #20435b;
  cursor: pointer;
}

.session-item:hover {
  border-color: #8cb7d7;
}

.session-item.active {
  border-color: #3b8fcb;
  background: #e8f3fb;
}

.session-title {
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-time {
  font-size: 11px;
  color: #628099;
}

.sidebar-footer {
  padding: 10px;
  border-top: 1px solid #d8e5f0;
}

.ghost-btn {
  width: 100%;
  height: 34px;
  border-radius: 10px;
  border: 1px solid #c8d9e7;
  background: #f7fbff;
  color: #3f637e;
  cursor: pointer;
}

.ghost-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.chat-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 18px 12px;
  border-bottom: 1px solid #d8e5f0;
  background: linear-gradient(180deg, #f7fbff 0%, #f1f7fd 100%);
}

.chat-title {
  margin: 0;
  font-size: 18px;
  letter-spacing: 0.2px;
  color: #13324a;
}

.subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: #5a768d;
}

.status-badge {
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #135a8f;
  background: #dbeaf6;
  border: 1px solid #bdd8ec;
}

@media (max-width: 768px) {
  .app-shell {
    padding: 8px;
  }

  .workspace {
    grid-template-columns: 1fr;
    height: calc(100vh - 20px);
    min-height: 560px;
    border-radius: 14px;
  }

  .session-sidebar {
    min-height: 220px;
    border-right: none;
    border-bottom: 1px solid #d8e5f0;
  }

  .session-list {
    max-height: 120px;
  }

  .chat-header {
    padding: 14px 12px 10px;
  }

  .chat-title {
    font-size: 17px;
  }
}
</style>
