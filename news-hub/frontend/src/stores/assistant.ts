import { defineStore } from 'pinia'
import { ref } from 'vue'
import { assistantApi, type ChatMessage, type ConversationThread } from '@/api/assistant'

export const useAssistantStore = defineStore('assistant', () => {
  // Chat state
  const messages = ref<ChatMessage[]>([])
  const streamingContent = ref('')
  const isStreaming = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const abortController = ref<AbortController | null>(null)
  const activeStreamToken = ref(0)

  // Conversation state
  const currentThreadId = ref<string | null>(null)
  const conversations = ref<ConversationThread[]>([])
  const conversationsTotal = ref(0)

  // UI state
  const chatMode = ref<'chat' | 'agent' | 'research'>('chat')
  const fairyOpen = ref(false)
  const sidebarOpen = ref(false)

  const RESEARCH_STATUS_RE = /^\[(Plan|Search|Select|Read|Extract|Search2|Read2|Done)\]/m
  const RESEARCH_FALLBACK_REPORT = [
    '## 研究结果',
    '',
    '研究流程已完成，但未收到报告正文。',
    '',
    '请重试一次；如果仍然出现该问题，请检查后端 deep research 日志。',
  ].join('\n')

  function ensureDeepResearchReport(content: string): string {
    const trimmed = content.trim()
    if (!trimmed) {
      return `[Done] 报告生成完成\n[REPORT_START]\n${RESEARCH_FALLBACK_REPORT}`
    }
    const hasReportMarker = trimmed.includes('[REPORT_START]') || trimmed.includes('\n---\n')
    if (hasReportMarker) return trimmed
    if (RESEARCH_STATUS_RE.test(trimmed)) {
      return `${trimmed}\n[REPORT_START]\n${RESEARCH_FALLBACK_REPORT}`
    }
    return trimmed
  }

  function ensureChatReply(content: string): string | null {
    const trimmed = content.trim()
    if (trimmed) return trimmed
    return null
  }

  // --- Chat Actions ---

  async function sendMessage(content: string, useAgent = false) {
    if (abortController.value && !abortController.value.signal.aborted) {
      abortController.value.abort()
    }

    const streamToken = activeStreamToken.value + 1
    activeStreamToken.value = streamToken

    const controller = new AbortController()
    abortController.value = controller

    messages.value.push({ role: 'user', content })
    loading.value = true
    error.value = null
    isStreaming.value = true
    streamingContent.value = ''

    const isCurrentStream = () => activeStreamToken.value === streamToken

    try {
      await assistantApi.chatStream(
        messages.value,
        (delta) => {
          if (!isCurrentStream()) return
          loading.value = false
          streamingContent.value += delta
        },
        () => {
          if (!isCurrentStream()) return
          const finalContent = ensureChatReply(streamingContent.value)
          if (finalContent) {
            messages.value.push({ role: 'assistant', content: finalContent })
          } else {
            error.value = '模型未返回内容，请稍后重试'
          }
          streamingContent.value = ''
          isStreaming.value = false
          loading.value = false
          if (abortController.value === controller) {
            abortController.value = null
          }
          loadConversations()
        },
        (err) => {
          if (!isCurrentStream()) return
          error.value = err
          isStreaming.value = false
          loading.value = false
          if (abortController.value === controller) {
            abortController.value = null
          }
        },
        controller.signal,
        {
          threadId: currentThreadId.value || undefined,
          onThreadId: (id) => {
            if (!isCurrentStream()) return
            currentThreadId.value = id
          },
          useAgent,
        }
      )
    } catch (err: unknown) {
      if (!isCurrentStream()) return
      const isAbortError = err instanceof DOMException && err.name === 'AbortError'
      let message = 'Failed to send message'
      if (err instanceof TypeError && (err.message.includes('fetch') || err.message.includes('network'))) {
        message = '网络连接失败，请检查网络后重试'
      } else if (err instanceof Error) {
        message = err.message.startsWith('HTTP') ? `服务器错误: ${err.message}` : err.message
      }
      if (!isAbortError && !controller.signal.aborted) {
        error.value = message
      }
      isStreaming.value = false
      loading.value = false
      if (abortController.value === controller) {
        abortController.value = null
      }
    }
  }

  async function sendDeepResearch(query: string) {
    if (abortController.value && !abortController.value.signal.aborted) {
      abortController.value.abort()
    }

    const streamToken = activeStreamToken.value + 1
    activeStreamToken.value = streamToken

    const controller = new AbortController()
    abortController.value = controller

    messages.value.push({ role: 'user', content: `[深度研究] ${query}` })
    loading.value = true
    error.value = null
    isStreaming.value = true
    streamingContent.value = ''

    const isCurrentStream = () => activeStreamToken.value === streamToken

    try {
      await assistantApi.deepResearchStream(
        query,
        (delta) => {
          if (!isCurrentStream()) return
          loading.value = false
          streamingContent.value += delta
        },
        () => {
          if (!isCurrentStream()) return
          const finalContent = ensureDeepResearchReport(streamingContent.value)
          messages.value.push({ role: 'assistant', content: finalContent })
          streamingContent.value = ''
          isStreaming.value = false
          loading.value = false
          if (abortController.value === controller) {
            abortController.value = null
          }
        },
        (err) => {
          if (!isCurrentStream()) return
          error.value = err
          isStreaming.value = false
          loading.value = false
          if (abortController.value === controller) {
            abortController.value = null
          }
        },
        controller.signal
      )
    } catch (err: unknown) {
      if (!isCurrentStream()) return
      const isAbortError = err instanceof DOMException && err.name === 'AbortError'
      let message = 'Research failed'
      if (err instanceof TypeError && (err.message.includes('fetch') || err.message.includes('network'))) {
        message = '网络连接失败，请检查网络后重试'
      } else if (err instanceof Error) {
        message = err.message.startsWith('HTTP') ? `服务器错误: ${err.message}` : err.message
      }
      if (!isAbortError && !controller.signal.aborted) {
        error.value = message
      }
      isStreaming.value = false
      loading.value = false
      if (abortController.value === controller) {
        abortController.value = null
      }
    }
  }

  function stopStreaming() {
    activeStreamToken.value += 1
    if (abortController.value) {
      abortController.value.abort()
      abortController.value = null
    }
    if (isStreaming.value && streamingContent.value) {
      messages.value.push({ role: 'assistant', content: streamingContent.value })
    }
    isStreaming.value = false
    streamingContent.value = ''
    loading.value = false
  }

  // --- Conversation Actions ---

  async function loadConversations() {
    try {
      const res = await assistantApi.listConversations()
      if (res.code === 200 && res.data) {
        conversations.value = res.data.threads
        conversationsTotal.value = res.data.total
      }
    } catch (e) {
      console.warn('Failed to load conversations:', e)
    }
  }

  function newThread() {
    currentThreadId.value = null
    messages.value = []
    error.value = null
    streamingContent.value = ''
    isStreaming.value = false
    sidebarOpen.value = false
  }

  function switchThread(threadId: string) {
    currentThreadId.value = threadId
    messages.value = []
    error.value = null
    streamingContent.value = ''
    isStreaming.value = false
    sidebarOpen.value = false
  }

  async function deleteThread(threadId: string) {
    try {
      await assistantApi.deleteConversation(threadId)
      conversations.value = conversations.value.filter(c => c.thread_id !== threadId)
      if (currentThreadId.value === threadId) {
        newThread()
      }
    } catch (e) {
      console.warn('Failed to delete conversation:', e)
    }
  }

  async function renameThread(threadId: string, title: string) {
    try {
      await assistantApi.updateConversation(threadId, title)
      const conv = conversations.value.find(c => c.thread_id === threadId)
      if (conv) conv.title = title
    } catch (e) {
      console.warn('Failed to rename conversation:', e)
    }
  }

  // --- UI Actions ---

  function toggleFairy() {
    fairyOpen.value = !fairyOpen.value
    if (fairyOpen.value && conversations.value.length === 0) {
      loadConversations()
    }
  }

  function toggleSidebar() {
    sidebarOpen.value = !sidebarOpen.value
    if (sidebarOpen.value) loadConversations()
  }

  function clearMessages() {
    messages.value = []
    error.value = null
    streamingContent.value = ''
    isStreaming.value = false
  }

  function clearError() {
    error.value = null
  }

  return {
    // Chat
    messages, streamingContent, isStreaming, loading, error, abortController,
    sendMessage, sendDeepResearch, stopStreaming, clearMessages, clearError,
    // Conversations
    currentThreadId, conversations, conversationsTotal,
    loadConversations, newThread, switchThread, deleteThread, renameThread,
    // UI
    chatMode, fairyOpen, sidebarOpen, toggleFairy, toggleSidebar,
  }
})
