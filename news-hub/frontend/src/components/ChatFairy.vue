<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onUnmounted, computed } from 'vue'
import { useAssistantStore } from '@/stores/assistant'
import { marked } from 'marked'

const store = useAssistantStore()
const inputText = ref('')
const messagesEl = ref<HTMLElement | null>(null)

// --- Drag state ---
const posRight = ref(24)
const posBottom = ref(24)
const isDragging = ref(false)
let dragStartX = 0
let dragStartY = 0
let dragStartRight = 0
let dragStartBottom = 0
let dragMoved = false

function onDragStart(e: MouseEvent) {
  isDragging.value = true
  dragMoved = false
  dragStartX = e.clientX
  dragStartY = e.clientY
  dragStartRight = posRight.value
  dragStartBottom = posBottom.value
  document.addEventListener('mousemove', onDragMove)
  document.addEventListener('mouseup', onDragEnd)
  e.preventDefault()
}

function onDragMove(e: MouseEvent) {
  const dx = e.clientX - dragStartX
  const dy = e.clientY - dragStartY
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) dragMoved = true
  const newRight = Math.max(0, dragStartRight - dx)
  const newBottom = Math.max(0, dragStartBottom - dy)
  // Keep within viewport
  const maxRight = window.innerWidth - 60
  const maxBottom = window.innerHeight - 60
  posRight.value = Math.min(newRight, maxRight)
  posBottom.value = Math.min(newBottom, maxBottom)
}

function onDragEnd() {
  isDragging.value = false
  document.removeEventListener('mousemove', onDragMove)
  document.removeEventListener('mouseup', onDragEnd)
}

function onBtnClick() {
  if (!dragMoved) store.toggleFairy()
}

const panelStyle = computed(() => ({
  right: `${posRight.value}px`,
  bottom: `${posBottom.value}px`,
}))

const btnStyle = computed(() => ({
  right: `${posRight.value}px`,
  bottom: `${posBottom.value}px`,
}))

const currentTitle = computed(() => {
  if (!store.currentThreadId) return '新对话'
  const conv = store.conversations.find(c => c.thread_id === store.currentThreadId)
  return conv?.title || '对话'
})

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

watch(() => store.streamingContent, scrollToBottom)
watch(() => store.messages.length, scrollToBottom)

function handleSend() {
  const text = inputText.value.trim()
  if (!text || store.isStreaming) return
  inputText.value = ''
  if (store.chatMode === 'research') {
    store.sendDeepResearch(text)
  } else if (store.chatMode === 'agent') {
    store.sendMessage(text, true)
  } else {
    store.sendMessage(text)
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
  if (e.key === 'Escape') {
    store.fairyOpen = false
  }
}

function handleGlobalKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && store.fairyOpen) {
    store.fairyOpen = false
  }
}

function formatTime(dateStr: string) {
  const d = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function renderMarkdown(text: string) {
  return marked.parse(text, { async: false }) as string
}

const RESEARCH_STATUS_RE = /^\[(Plan|Search|Select|Read|Extract|Search2|Read2|Done)\]/

function isResearchStatusLine(line: string): boolean {
  const trimmed = line.trim()
  return trimmed.length > 0 && RESEARCH_STATUS_RE.test(trimmed)
}

function splitResearch(text: string): { thinking: string; report: string } | null {
  // Preferred protocol marker from backend.
  const explicitMarkers = ['\n[REPORT_START]\n', '[REPORT_START]\n']
  for (const marker of explicitMarkers) {
    const idx = text.indexOf(marker)
    if (idx === -1) continue
    return {
      thinking: text.slice(0, idx).trim(),
      report: text.slice(idx + marker.length).trim(),
    }
  }

  // Backward compatibility with old separator format.
  const legacyMarkers = ['\n---\n\n', '\n---\n']
  for (const marker of legacyMarkers) {
    const idx = text.indexOf(marker)
    if (idx === -1) continue
    const thinking = text.slice(0, idx).trim()
    if (thinking.split('\n').some(isResearchStatusLine)) {
      return {
        thinking,
        report: text.slice(idx + marker.length).trim(),
      }
    }
  }

  // Fallback: parse leading status lines when separator is missing.
  const lines = text.split('\n')
  const thinkingLines: string[] = []
  let seenStatus = false
  let reportStartIndex = -1

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (isResearchStatusLine(line)) {
      seenStatus = true
      thinkingLines.push(line)
      continue
    }
    if (!seenStatus) continue
    if (!line.trim()) {
      thinkingLines.push(line)
      continue
    }
    reportStartIndex = i
    break
  }

  if (!seenStatus) return null
  if (reportStartIndex === -1) {
    return { thinking: text.trim(), report: '' }
  }
  return {
    thinking: thinkingLines.join('\n').trim(),
    report: lines.slice(reportStartIndex).join('\n').trim(),
  }
}

const thinkingExpanded = ref<Record<number, boolean>>({})
function toggleThinking(idx: number) {
  thinkingExpanded.value[idx] = !thinkingExpanded.value[idx]
}

// For streaming content
const streamThinkingOpen = ref(false)

onMounted(() => {
  document.addEventListener('keydown', handleGlobalKeydown)
})
onUnmounted(() => {
  document.removeEventListener('keydown', handleGlobalKeydown)
})
</script>

<template>
  <Teleport to="body">
    <!-- Floating Button -->
    <button
      v-if="!store.fairyOpen"
      class="fairy-btn"
      :style="btnStyle"
      :class="{ dragging: isDragging }"
      @mousedown="onDragStart"
      @click="onBtnClick"
      aria-label="打开 AI 助手"
    >
      <span class="fairy-icon">🧚</span>
    </button>

    <!-- Chat Panel -->
    <Transition name="fairy-panel">
      <div v-if="store.fairyOpen" class="fairy-panel glass-strong" :style="panelStyle">
        <!-- Header (draggable) -->
        <div class="fairy-header" @mousedown="onDragStart" :class="{ dragging: isDragging }">
          <div class="fairy-header-left">
            <span class="fairy-avatar">🧚</span>
            <span class="fairy-title">{{ currentTitle }}</span>
          </div>
          <div class="fairy-header-actions">
            <button class="fairy-icon-btn" @click="store.newThread()" title="新对话">➕</button>
            <button class="fairy-icon-btn" @click="store.toggleSidebar()" title="对话历史">📋</button>
            <button class="fairy-icon-btn" @click="store.fairyOpen = false" title="关闭">✕</button>
          </div>
        </div>

        <!-- Sidebar -->
        <Transition name="sidebar-slide">
          <div v-if="store.sidebarOpen" class="fairy-sidebar">
            <div class="sidebar-header">
              <span>对话历史</span>
              <button class="fairy-icon-btn" @click="store.sidebarOpen = false">✕</button>
            </div>
            <div class="sidebar-list">
              <div
                v-for="conv in store.conversations"
                :key="conv.thread_id"
                class="sidebar-item"
                :class="{ active: conv.thread_id === store.currentThreadId }"
                @click="store.switchThread(conv.thread_id)"
              >
                <div class="sidebar-item-title">{{ conv.title }}</div>
                <div class="sidebar-item-meta">
                  {{ formatTime(conv.last_message_at) }} · {{ conv.message_count }} 条
                </div>
                <button
                  class="sidebar-item-delete"
                  @click.stop="store.deleteThread(conv.thread_id)"
                  title="删除"
                >🗑️</button>
              </div>
              <div v-if="store.conversations.length === 0" class="sidebar-empty">
                暂无对话记录
              </div>
            </div>
          </div>
        </Transition>

        <!-- Messages -->
        <div ref="messagesEl" class="fairy-messages">
          <!-- Empty state -->
          <div v-if="store.messages.length === 0 && !store.isStreaming" class="fairy-empty">
            <div class="fairy-empty-icon">🧚</div>
            <p>有什么可以帮你的？</p>
            <div class="fairy-suggestions">
              <button class="suggestion-chip" @click="inputText = '今天有什么新闻？'">今天有什么新闻？</button>
              <button class="suggestion-chip" @click="inputText = '帮我总结一下最近的热点'">总结最近热点</button>
            </div>
          </div>

          <!-- Message bubbles -->
          <div
            v-for="(msg, i) in store.messages"
            :key="i"
            class="fairy-msg"
            :class="msg.role"
          >
            <div class="msg-avatar">{{ msg.role === 'user' ? '👤' : '🧚' }}</div>
            <div v-if="msg.role === 'assistant' && splitResearch(msg.content)" class="msg-bubble">
              <div class="thinking-block" :class="{ open: thinkingExpanded[i] }" @click="toggleThinking(i)">
                <span class="thinking-toggle">{{ thinkingExpanded[i] ? '▼' : '▶' }}</span>
                <span class="thinking-label">思考过程</span>
                <span class="thinking-summary" v-if="!thinkingExpanded[i]">{{ splitResearch(msg.content)!.thinking.split('\n').length }} 步</span>
              </div>
              <div v-if="thinkingExpanded[i]" class="thinking-content">
                <div v-for="(line, li) in splitResearch(msg.content)!.thinking.split('\n').filter(Boolean)" :key="li" class="thinking-line">{{ line }}</div>
              </div>
              <div v-if="splitResearch(msg.content)!.report" v-html="renderMarkdown(splitResearch(msg.content)!.report)"></div>
            </div>
            <div v-else class="msg-bubble" v-html="msg.role === 'assistant' ? renderMarkdown(msg.content) : msg.content"></div>
          </div>

          <!-- Streaming -->
          <div v-if="store.isStreaming || store.loading" class="fairy-msg assistant">
            <div class="msg-avatar">🧚</div>
            <div class="msg-bubble">
              <template v-if="store.streamingContent && splitResearch(store.streamingContent)">
                <div class="thinking-block" :class="{ open: streamThinkingOpen }" @click="streamThinkingOpen = !streamThinkingOpen">
                  <span class="thinking-toggle">{{ streamThinkingOpen ? '▼' : '▶' }}</span>
                  <span class="thinking-label">思考中...</span>
                </div>
                <div v-if="streamThinkingOpen" class="thinking-content">
                  <div v-for="(line, li) in splitResearch(store.streamingContent)!.thinking.split('\n').filter(Boolean)" :key="li" class="thinking-line">{{ line }}</div>
                </div>
                <div v-if="splitResearch(store.streamingContent)!.report" v-html="renderMarkdown(splitResearch(store.streamingContent)!.report)"></div>
                <span v-else class="typing-dots">生成报告中</span>
              </template>
              <template v-else>
                <span v-if="store.streamingContent" v-html="renderMarkdown(store.streamingContent)"></span>
                <span v-else class="typing-dots">思考中</span>
              </template>
              <span class="cursor-blink">|</span>
            </div>
          </div>

          <!-- Error -->
          <div v-if="store.error" class="fairy-error">
            ⚠️ {{ store.error }}
            <button class="fairy-icon-btn" @click="store.clearError()">✕</button>
          </div>
        </div>

        <!-- Input Area -->
        <div class="fairy-input-area">
          <!-- Mode tabs -->
          <div class="mode-tabs">
            <button
              class="mode-tab"
              :class="{ active: store.chatMode === 'chat' }"
              @click="store.chatMode = 'chat'"
            >对话</button>
            <button
              class="mode-tab"
              :class="{ active: store.chatMode === 'agent' }"
              @click="store.chatMode = 'agent'"
            >智能助手</button>
            <button
              class="mode-tab"
              :class="{ active: store.chatMode === 'research' }"
              @click="store.chatMode = 'research'"
            >深度研究</button>
          </div>
          <div class="input-row">
            <textarea
              v-model="inputText"
              :placeholder="store.chatMode === 'research' ? '输入研究主题...' : store.chatMode === 'agent' ? '输入问题（可搜索/抓取）...' : '输入消息...'"
              rows="1"
              @keydown="handleKeydown"
              :disabled="store.isStreaming"
            ></textarea>
            <button
              v-if="store.isStreaming"
              class="send-btn stop"
              @click="store.stopStreaming()"
            >⏹️</button>
            <button
              v-else
              class="send-btn"
              :disabled="!inputText.trim()"
              @click="handleSend"
            >📤</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* Floating Button */
.fairy-btn {
  position: fixed;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(135deg, var(--color-primary-400), var(--color-secondary-400));
  box-shadow: 0 4px 20px rgba(168, 85, 247, 0.4);
  cursor: grab;
  z-index: 500;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s, box-shadow 0.2s;
  animation: fairy-float 3s ease-in-out infinite;
  user-select: none;
}
.fairy-btn.dragging {
  cursor: grabbing;
  animation: none;
}
.fairy-btn:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 28px rgba(168, 85, 247, 0.6);
}
.fairy-icon { font-size: 28px; }

@keyframes fairy-float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-6px); }
}

/* Panel */
.fairy-panel {
  position: fixed;
  width: 400px;
  height: 600px;
  max-height: calc(100vh - 48px);
  border-radius: var(--radius-2xl);
  display: flex;
  flex-direction: column;
  z-index: 500;
  overflow: hidden;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.15);
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.5);
}

/* Panel transition */
.fairy-panel-enter-active { transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1); }
.fairy-panel-leave-active { transition: all 0.2s ease-in; }
.fairy-panel-enter-from { opacity: 0; transform: scale(0.8) translateY(20px); }
.fairy-panel-leave-to { opacity: 0; transform: scale(0.9) translateY(10px); }

/* Header */
.fairy-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  background: linear-gradient(135deg, rgba(236, 72, 153, 0.08), rgba(168, 85, 247, 0.08));
  cursor: grab;
  user-select: none;
}
.fairy-header.dragging { cursor: grabbing; }
.fairy-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.fairy-avatar { font-size: 20px; }
.fairy-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--color-neutral-800);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fairy-header-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}
.fairy-icon-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: var(--radius-md);
  font-size: 14px;
  transition: background 0.15s;
  color: var(--color-neutral-500);
}
.fairy-icon-btn:hover {
  background: rgba(0, 0, 0, 0.06);
}

/* Sidebar */
.fairy-sidebar {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
  z-index: 10;
  display: flex;
  flex-direction: column;
}
.sidebar-slide-enter-active { transition: transform 0.25s ease-out; }
.sidebar-slide-leave-active { transition: transform 0.2s ease-in; }
.sidebar-slide-enter-from { transform: translateX(-100%); }
.sidebar-slide-leave-to { transform: translateX(-100%); }

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  font-weight: 600;
  font-size: 14px;
}
.sidebar-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.sidebar-item {
  padding: 10px 12px;
  border-radius: var(--radius-lg);
  cursor: pointer;
  position: relative;
  transition: background 0.15s;
}
.sidebar-item:hover { background: rgba(168, 85, 247, 0.06); }
.sidebar-item.active { background: rgba(168, 85, 247, 0.12); }
.sidebar-item-title {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding-right: 24px;
}
.sidebar-item-meta {
  font-size: 11px;
  color: var(--color-neutral-400);
  margin-top: 2px;
}
.sidebar-item-delete {
  position: absolute;
  top: 10px;
  right: 8px;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 12px;
  opacity: 0;
  transition: opacity 0.15s;
}
.sidebar-item:hover .sidebar-item-delete { opacity: 0.6; }
.sidebar-item-delete:hover { opacity: 1 !important; }
.sidebar-empty {
  text-align: center;
  color: var(--color-neutral-400);
  padding: 40px 16px;
  font-size: 13px;
}

/* Messages */
.fairy-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.fairy-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 8px;
  color: var(--color-neutral-500);
}
.fairy-empty-icon {
  font-size: 48px;
  animation: fairy-float 3s ease-in-out infinite;
}
.fairy-empty p { font-size: 14px; margin: 0; }
.fairy-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
  justify-content: center;
}
.suggestion-chip {
  background: rgba(168, 85, 247, 0.08);
  border: 1px solid rgba(168, 85, 247, 0.15);
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  color: var(--color-neutral-700);
}
.suggestion-chip:hover {
  background: rgba(168, 85, 247, 0.15);
  border-color: rgba(168, 85, 247, 0.3);
}

/* Message bubbles */
.fairy-msg {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.fairy-msg.user {
  flex-direction: row-reverse;
}
.msg-avatar {
  font-size: 18px;
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.msg-bubble {
  max-width: 80%;
  padding: 8px 12px;
  border-radius: 14px;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-word;
}
.fairy-msg.user .msg-bubble {
  background: linear-gradient(135deg, var(--color-primary-400), var(--color-secondary-400));
  color: white;
  border-bottom-right-radius: 4px;
}
.fairy-msg.assistant .msg-bubble {
  background: rgba(0, 0, 0, 0.04);
  color: var(--color-neutral-800);
  border-bottom-left-radius: 4px;
}
.msg-bubble :deep(p) { margin: 0 0 6px; }
.msg-bubble :deep(p:last-child) { margin-bottom: 0; }
.msg-bubble :deep(code) {
  background: rgba(0, 0, 0, 0.06);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
}
.msg-bubble :deep(pre) {
  background: rgba(0, 0, 0, 0.06);
  padding: 8px;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 12px;
}
.msg-bubble :deep(h1), .msg-bubble :deep(h2), .msg-bubble :deep(h3) {
  font-size: 14px;
  font-weight: 600;
  margin: 8px 0 4px;
}

.typing-dots {
  color: var(--color-neutral-400);
  font-size: 12px;
}

/* Thinking block (collapsible) */
.thinking-block {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  margin: -4px -4px 6px;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 12px;
  color: var(--color-neutral-500);
  background: rgba(168, 85, 247, 0.05);
  border: 1px solid rgba(168, 85, 247, 0.1);
  transition: background 0.15s;
  user-select: none;
}
.thinking-block:hover {
  background: rgba(168, 85, 247, 0.1);
}
.thinking-toggle {
  font-size: 10px;
  flex-shrink: 0;
  width: 12px;
}
.thinking-label {
  font-weight: 500;
  color: var(--color-neutral-600);
}
.thinking-summary {
  color: var(--color-neutral-400);
  font-size: 11px;
}
.thinking-content {
  padding: 6px 8px;
  margin-bottom: 8px;
  border-left: 2px solid rgba(168, 85, 247, 0.2);
  font-size: 11px;
  color: var(--color-neutral-500);
  line-height: 1.6;
  max-height: 200px;
  overflow-y: auto;
}
.thinking-line {
  padding: 1px 0;
  font-family: 'Menlo', 'Consolas', monospace;
}
.cursor-blink {
  animation: blink 1s step-end infinite;
  color: var(--color-primary-400);
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.fairy-error {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: rgba(239, 68, 68, 0.08);
  border-radius: var(--radius-lg);
  font-size: 12px;
  color: var(--color-error);
}

/* Input Area */
.fairy-input-area {
  border-top: 1px solid rgba(0, 0, 0, 0.06);
  padding: 8px 12px 12px;
}
.mode-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}
.mode-tab {
  flex: 1;
  padding: 4px 0;
  border: none;
  background: rgba(0, 0, 0, 0.04);
  border-radius: var(--radius-md);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  color: var(--color-neutral-500);
}
.mode-tab.active {
  background: linear-gradient(135deg, rgba(236, 72, 153, 0.12), rgba(168, 85, 247, 0.12));
  color: var(--color-primary-600);
  font-weight: 600;
}
.input-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}
.input-row textarea {
  flex: 1;
  resize: none;
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 12px;
  padding: 8px 12px;
  font-size: 13px;
  font-family: inherit;
  background: rgba(255, 255, 255, 0.6);
  outline: none;
  transition: border-color 0.15s;
  max-height: 80px;
}
.input-row textarea:focus {
  border-color: var(--color-primary-300);
}
.send-btn {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(135deg, var(--color-primary-400), var(--color-secondary-400));
  cursor: pointer;
  font-size: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.15s, transform 0.15s;
  flex-shrink: 0;
}
.send-btn:disabled { opacity: 0.4; cursor: default; }
.send-btn:not(:disabled):hover { transform: scale(1.05); }
.send-btn.stop {
  background: var(--color-error);
}

/* Mobile */
@media (max-width: 480px) {
  .fairy-panel {
    width: calc(100vw - 16px);
    height: calc(100vh - 16px);
    bottom: 8px;
    right: 8px;
    border-radius: var(--radius-xl);
  }
}
</style>
