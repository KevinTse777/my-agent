<template>
  <div class="app-shell">
    <div class="chat-card">
      <header class="chat-header">
        <div>
          <h1 class="title">智能对话助手</h1>
          <p class="subtitle">MVP · 带搜索引用</p>
        </div>
        <div class="status-badge">{{ loading ? '请求中' : '就绪' }}</div>
      </header>

      <MessageList :messages="messages" :loading="loading" />
      <ChatInput :loading="loading" :error="errorMessage" @send="onSend" />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import MessageList from './components/MessageList.vue'
import ChatInput from './components/ChatInput.vue'
import { sendChatMessage } from './api/chat'

let seq = 0

const messages = ref([
  {
    id: ++seq,
    role: 'assistant',
    content: '你好，我是你的学习助手。涉及外部信息的问题我会附带可点击的 src 引用。',
    toolsUsed: [],
    sources: [],
  },
])

const loading = ref(false)
const errorMessage = ref('')

async function onSend(text) {
  if (!text.trim() || loading.value) {
    return
  }

  errorMessage.value = ''

  messages.value.push({
    id: ++seq,
    role: 'user',
    content: text,
    toolsUsed: [],
    sources: [],
  })

  loading.value = true

  try {
    const result = await sendChatMessage(text)
    messages.value.push({
      id: ++seq,
      role: 'assistant',
      content: result.answer || '助手未返回文本内容',
      toolsUsed: result.toolsUsed || [],
      sources: result.sources || [],
    })
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
  align-items: stretch;
}

.chat-card {
  width: min(980px, 100%);
  height: calc(100vh - 48px);
  min-height: 620px;
  background: #fafdff;
  border: 1px solid #cfdfeb;
  border-radius: 18px;
  box-shadow: 0 12px 35px rgba(38, 78, 110, 0.08);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 18px 18px 14px;
  border-bottom: 1px solid #d8e5f0;
  background: linear-gradient(180deg, #f7fbff 0%, #f1f7fd 100%);
}

.title {
  margin: 0;
  font-size: 20px;
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
    padding: 10px;
  }

  .chat-card {
    height: calc(100vh - 20px);
    min-height: 520px;
    border-radius: 14px;
  }

  .chat-header {
    padding: 14px 12px 10px;
  }

  .title {
    font-size: 17px;
  }
}
</style>
