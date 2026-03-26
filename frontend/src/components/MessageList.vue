<template>
  <div class="message-list" ref="listRef">
    <div
      v-for="msg in messages"
      :key="msg.id"
      class="message-row"
      :class="msg.role === 'user' ? 'is-user' : 'is-assistant'"
    >
      <div class="message-bubble">
        <div class="message-meta">
          <span class="role-label">{{ msg.role === 'user' ? '你' : '助手' }}</span>
          <span v-if="msg.toolsUsed && msg.toolsUsed.length" class="tools-label">
            工具: {{ msg.toolsUsed.join(', ') }}
          </span>
        </div>

        <div class="message-text">{{ msg.content }}</div>

        <SourceLinks
          v-if="msg.role === 'assistant' && msg.sources && msg.sources.length"
          :sources="msg.sources"
        />
      </div>
    </div>

    <div v-if="loading" class="message-row is-assistant">
      <div class="message-bubble loading-bubble" aria-label="loading">
        <span class="dot"></span>
        <span class="dot"></span>
        <span class="dot"></span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import SourceLinks from './SourceLinks.vue'

const props = defineProps({
  messages: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
})

const listRef = ref(null)

async function scrollToBottom() {
  await nextTick()
  if (!listRef.value) {
    return
  }
  listRef.value.scrollTop = listRef.value.scrollHeight
}

watch(
  () => [props.messages.length, props.loading],
  () => {
    scrollToBottom()
  },
  { immediate: true }
)
</script>

<style scoped>
.message-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px 20px 10px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.message-row {
  display: flex;
}

.message-row.is-user {
  justify-content: flex-end;
}

.message-row.is-assistant {
  justify-content: flex-start;
}

.message-bubble {
  max-width: min(78%, 760px);
  border-radius: 14px;
  padding: 12px 14px;
  line-height: 1.6;
  border: 1px solid transparent;
  word-break: break-word;
  white-space: pre-wrap;
}

.is-user .message-bubble {
  background: linear-gradient(140deg, #0b79d0, #2f8ed8);
  color: #f5f9ff;
  border-color: #2e82c5;
}

.is-assistant .message-bubble {
  background: #ffffff;
  color: #1b3448;
  border-color: #d4e3ef;
}

.message-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12px;
}

.role-label {
  font-weight: 600;
  opacity: 0.9;
}

.tools-label {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(13, 110, 194, 0.12);
  color: #0b5fa7;
}

.message-text {
  font-size: 14px;
}

.loading-bubble {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #6a8aa5;
  animation: blink 1s infinite ease-in-out;
}

.dot:nth-child(2) {
  animation-delay: 0.2s;
}

.dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes blink {
  0%,
  80%,
  100% {
    opacity: 0.3;
    transform: translateY(0);
  }
  40% {
    opacity: 1;
    transform: translateY(-2px);
  }
}

@media (max-width: 768px) {
  .message-list {
    padding: 14px 12px 6px;
  }

  .message-bubble {
    max-width: 92%;
  }
}
</style>
