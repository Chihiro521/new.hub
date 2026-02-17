<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAssistantStore } from '@/stores/assistant'

const router = useRouter()
const authStore = useAuthStore()
const assistantStore = useAssistantStore()

const userInput = ref('')
const messagesContainer = ref<HTMLElement | null>(null)

function handleLogout() {
  authStore.logout()
  router.push('/login')
}

async function handleSend() {
  const content = userInput.value.trim()
  if (!content || assistantStore.loading || assistantStore.isStreaming) return

  userInput.value = ''
  await assistantStore.sendMessage(content)
}

function handleStop() {
  assistantStore.stopStreaming()
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

// Auto-scroll on new messages or streaming updates
watch(
  () => [assistantStore.messages.length, assistantStore.streamingContent],
  () => {
    scrollToBottom()
  },
  { deep: true }
)

const suggestedPrompts = [
  "总结最近的热点新闻",
  "帮我发现新的科技类信息源",
  "如何优化我的阅读标签规则？",
  "分析一下当前的新闻趋势"
]

function usePrompt(prompt: string) {
  userInput.value = prompt
  handleSend()
}
</script>

<template>
  <div class="assistant-page">
    <!-- Header -->
    <header class="header glass">
      <div class="header-left">
        <h1 class="logo gradient-text">News Hub</h1>
        <nav class="nav">
          <router-link to="/" class="nav-link">首页</router-link>
          <router-link to="/sources" class="nav-link">订阅源</router-link>
          <router-link to="/search" class="nav-link">搜索</router-link>
          <router-link to="/assistant" class="nav-link active">AI 助手</router-link>
        </nav>
      </div>
      <div class="user-menu">
        <span class="username">{{ authStore.username }}</span>
        <button class="btn-secondary logout-btn" @click="handleLogout">退出</button>
      </div>
    </header>

    <main class="main-content">
      <div class="chat-container glass">
        <!-- Messages Area -->
        <div class="messages-area" ref="messagesContainer">
          <!-- Empty State -->
          <div v-if="assistantStore.messages.length === 0" class="empty-state">
            <div class="ai-avatar-large">🤖</div>
            <h2>我是你的 AI 助手</h2>
            <p>我可以帮你总结新闻、发现源、分类文章，或者只是聊聊天。</p>
            <div class="suggestions">
              <button 
                v-for="prompt in suggestedPrompts" 
                :key="prompt"
                class="suggestion-btn"
                @click="usePrompt(prompt)"
              >
                {{ prompt }}
              </button>
            </div>
          </div>

          <!-- Message List -->
          <div v-else class="message-list">
            <div 
              v-for="(msg, index) in assistantStore.messages" 
              :key="index"
              class="message-row"
              :class="msg.role"
            >
              <div class="avatar">
                {{ msg.role === 'user' ? '👤' : '🤖' }}
              </div>
              <div class="message-bubble">
                <div class="message-content">{{ msg.content }}</div>
              </div>
            </div>

            <!-- Streaming Message -->
            <div v-if="assistantStore.isStreaming" class="message-row assistant">
              <div class="avatar">🤖</div>
              <div class="message-bubble streaming">
                <div class="message-content">
                  {{ assistantStore.streamingContent }}<span class="cursor">|</span>
                </div>
              </div>
            </div>
            
            <!-- Error Message -->
            <div v-if="assistantStore.error" class="error-message">
              ⚠️ {{ assistantStore.error }}
            </div>
          </div>
        </div>

        <!-- Input Area -->
        <div class="input-area glass">
          <div class="input-wrapper">
            <textarea 
              v-model="userInput"
              placeholder="输入你的问题..."
              @keydown.enter.prevent="handleSend"
              :disabled="assistantStore.isStreaming"
              rows="1"
            ></textarea>
            <button 
              v-if="assistantStore.isStreaming"
              class="stop-btn"
              @click="handleStop"
            >
              ⏹️ 停止
            </button>
            <button 
              v-else
              class="send-btn"
              @click="handleSend"
              :disabled="!userInput.trim() || assistantStore.loading"
            >
              📤 发送
            </button>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.assistant-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-canvas);
}

/* Header (Shared) */
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--color-neutral-200);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 2rem;
}

.logo {
  font-family: var(--font-display);
  font-size: 1.5rem;
  font-weight: 700;
}

.nav {
  display: flex;
  gap: 1rem;
}

.nav-link {
  color: var(--color-neutral-600);
  text-decoration: none;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  transition: all 0.2s;
}

.nav-link:hover, .nav-link.active {
  background: rgba(255, 255, 255, 0.5);
  color: var(--color-primary-600);
}

.user-menu {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.username {
  color: var(--color-neutral-600);
  font-weight: 500;
}

.logout-btn {
  padding: 0.5rem 1rem;
  font-size: 0.9rem;
  border: 1px solid var(--color-neutral-200);
  border-radius: 0.5rem;
  background: transparent;
  cursor: pointer;
}

/* Main Content */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  max-width: 1000px;
  margin: 0 auto;
  width: 100%;
  padding: 1rem;
  height: calc(100vh - 80px); /* Adjust based on header height */
}

.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-xl);
  overflow: hidden;
  background: rgba(255, 255, 255, 0.5);
  border: 1px solid var(--color-neutral-200);
  position: relative;
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  scroll-behavior: smooth;
}

/* Empty State */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--color-neutral-500);
  text-align: center;
}

.ai-avatar-large {
  font-size: 4rem;
  margin-bottom: 1rem;
  animation: float 3s ease-in-out infinite;
}

.suggestions {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1rem;
  margin-top: 2rem;
  max-width: 600px;
}

.suggestion-btn {
  padding: 1rem;
  background: white;
  border: 1px solid var(--color-neutral-200);
  border-radius: var(--radius-lg);
  color: var(--color-neutral-700);
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}

.suggestion-btn:hover {
  border-color: var(--color-primary-300);
  background: var(--color-primary-50);
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}

/* Messages */
.message-row {
  display: flex;
  gap: 1rem;
  max-width: 80%;
}

.message-row.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.message-row.assistant {
  align-self: flex-start;
}

.avatar {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 50%;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  border: 1px solid var(--color-neutral-200);
  flex-shrink: 0;
}

.message-bubble {
  padding: 1rem 1.5rem;
  border-radius: var(--radius-xl);
  line-height: 1.6;
  position: relative;
  word-break: break-word;
}

.user .message-bubble {
  background: var(--gradient-primary);
  color: white;
  border-bottom-right-radius: var(--radius-xs);
}

.assistant .message-bubble {
  background: white;
  border: 1px solid var(--color-neutral-200);
  color: var(--color-neutral-800);
  border-bottom-left-radius: var(--radius-xs);
}

.cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  background: currentColor;
  margin-left: 2px;
  vertical-align: middle;
  animation: blink 1s step-end infinite;
}

.error-message {
  align-self: center;
  background: var(--color-error-50);
  color: var(--color-error-600);
  padding: 0.5rem 1rem;
  border-radius: var(--radius-full);
  font-size: 0.9rem;
  border: 1px solid var(--color-error-200);
}

/* Input Area */
.input-area {
  padding: 1.5rem;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(12px);
  border-top: 1px solid var(--color-neutral-200);
}

.input-wrapper {
  display: flex;
  gap: 1rem;
  background: white;
  padding: 0.5rem;
  border-radius: var(--radius-2xl);
  border: 1px solid var(--color-neutral-300);
  box-shadow: var(--shadow-sm);
  transition: all 0.2s;
}

.input-wrapper:focus-within {
  border-color: var(--color-primary-400);
  box-shadow: 0 0 0 3px var(--color-primary-100);
}

textarea {
  flex: 1;
  border: none;
  padding: 0.75rem 1rem;
  font-family: inherit;
  font-size: 1rem;
  resize: none;
  outline: none;
  background: transparent;
  max-height: 150px;
}

.send-btn, .stop-btn {
  padding: 0.5rem 1.5rem;
  border-radius: var(--radius-xl);
  border: none;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.send-btn {
  background: var(--color-primary-600);
  color: white;
}

.send-btn:hover:not(:disabled) {
  background: var(--color-primary-700);
}

.send-btn:disabled {
  background: var(--color-neutral-300);
  cursor: not-allowed;
}

.stop-btn {
  background: var(--color-neutral-100);
  color: var(--color-neutral-700);
  border: 1px solid var(--color-neutral-300);
}

.stop-btn:hover {
  background: var(--color-neutral-200);
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

/* Dark Mode Overrides */
[data-theme="dark"] .header,
[data-theme="dark"] .input-area {
  background: rgba(30, 30, 30, 0.8);
  border-color: var(--color-neutral-700);
}

[data-theme="dark"] .chat-container {
  background: rgba(30, 30, 30, 0.5);
  border-color: var(--color-neutral-700);
}

[data-theme="dark"] .assistant .message-bubble {
  background: var(--color-neutral-800);
  border-color: var(--color-neutral-700);
  color: var(--color-neutral-200);
}

[data-theme="dark"] .input-wrapper {
  background: var(--color-neutral-800);
  border-color: var(--color-neutral-700);
}

[data-theme="dark"] textarea {
  color: var(--color-neutral-200);
}

[data-theme="dark"] .suggestion-btn {
  background: var(--color-neutral-800);
  border-color: var(--color-neutral-700);
  color: var(--color-neutral-300);
}

[data-theme="dark"] .suggestion-btn:hover {
  border-color: var(--color-primary-600);
  background: rgba(236, 72, 153, 0.1);
}

[data-theme="dark"] .avatar {
  background: var(--color-neutral-800);
  border-color: var(--color-neutral-700);
}
</style>
