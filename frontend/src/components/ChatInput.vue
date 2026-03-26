<template>
  <div class="chat-input-wrap">
    <form class="chat-input-form" @submit.prevent="handleSubmit">
      <textarea
        v-model="inputValue"
        class="chat-textarea"
        :disabled="loading"
        rows="1"
        placeholder="输入你的问题，按 Enter 发送，Shift + Enter 换行"
        @keydown="handleKeydown"
      ></textarea>
      <button class="send-btn" type="submit" :disabled="loading || !canSend">
        {{ loading ? '发送中...' : '发送' }}
      </button>
    </form>
    <p v-if="error" class="error-text">{{ error }}</p>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  loading: {
    type: Boolean,
    default: false,
  },
  error: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['send'])
const inputValue = ref('')
const canSend = computed(() => inputValue.value.trim().length > 0)

function handleSubmit() {
  const text = inputValue.value.trim()
  if (!text || props.loading) {
    return
  }
  emit('send', text)
  inputValue.value = ''
}

function handleKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleSubmit()
  }
}
</script>

<style scoped>
.chat-input-wrap {
  border-top: 1px solid #d5e3ee;
  background: #f8fbff;
  padding: 14px;
}

.chat-input-form {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.chat-textarea {
  flex: 1;
  resize: none;
  min-height: 44px;
  max-height: 140px;
  border: 1px solid #bfd1df;
  border-radius: 12px;
  padding: 10px 12px;
  font-size: 14px;
  line-height: 1.5;
  background: #ffffff;
  color: #153349;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.chat-textarea:focus {
  border-color: #3a8fce;
  box-shadow: 0 0 0 3px rgba(58, 143, 206, 0.14);
}

.chat-textarea:disabled {
  background: #eef4f9;
  cursor: not-allowed;
}

.send-btn {
  height: 44px;
  border: 1px solid #2d7fbe;
  background: #237fc3;
  color: #f2f8ff;
  border-radius: 12px;
  padding: 0 18px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s, border-color 0.2s;
}

.send-btn:hover:not(:disabled) {
  background: #1c73b2;
  border-color: #226ea8;
}

.send-btn:disabled {
  background: #a8bfd2;
  border-color: #9ab4c8;
  cursor: not-allowed;
}

.error-text {
  color: #c13b3b;
  font-size: 13px;
  margin: 10px 2px 0;
}

@media (max-width: 768px) {
  .chat-input-wrap {
    padding: 10px;
  }

  .chat-input-form {
    gap: 8px;
  }

  .send-btn {
    height: 42px;
    padding: 0 14px;
  }
}
</style>
