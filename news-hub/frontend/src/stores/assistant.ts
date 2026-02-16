import { defineStore } from 'pinia'
import { ref } from 'vue'
import { assistantApi, type ChatMessage } from '@/api/assistant'

export const useAssistantStore = defineStore('assistant', () => {
  // State
  const messages = ref<ChatMessage[]>([])
  const streamingContent = ref('')
  const isStreaming = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const abortController = ref<AbortController | null>(null)

  // Actions
  async function sendMessage(content: string) {
    // Add user message
    messages.value.push({ role: 'user', content })
    
    loading.value = true
    error.value = null
    isStreaming.value = true
    streamingContent.value = ''
    
    // Create new abort controller
    abortController.value = new AbortController()

    try {
      await assistantApi.chatStream(
        messages.value,
        (delta) => {
          loading.value = false // First token received, stop loading spinner
          streamingContent.value += delta
        },
        () => {
          // Done
          messages.value.push({ role: 'assistant', content: streamingContent.value })
          streamingContent.value = ''
          isStreaming.value = false
          loading.value = false
          abortController.value = null
        },
        (err) => {
          error.value = err
          isStreaming.value = false
          loading.value = false
          abortController.value = null
        },
        abortController.value.signal
      )
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to send message'
      // Only set error if not aborted
      if (abortController.value && !abortController.value.signal.aborted) {
        error.value = message
      }
      isStreaming.value = false
      loading.value = false
      abortController.value = null
    }
  }

  function stopStreaming() {
    if (abortController.value) {
      abortController.value.abort()
      abortController.value = null
    }
    if (isStreaming.value && streamingContent.value) {
      // Save partial response
      messages.value.push({ role: 'assistant', content: streamingContent.value })
    }
    isStreaming.value = false
    streamingContent.value = ''
    loading.value = false
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
    messages,
    streamingContent,
    isStreaming,
    loading,
    error,
    abortController,
    sendMessage,
    stopStreaming,
    clearMessages,
    clearError
  }
})
