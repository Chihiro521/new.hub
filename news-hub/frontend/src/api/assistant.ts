import apiClient from './client'
import type { ApiResponse } from './client'

// TypeScript interfaces
export interface ChatMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface SummarizeResult {
  news_id: string
  summary: string
  method: string  // 'ai' or 'extractive'
}

export interface ClassifyResult {
  news_id: string
  suggested_tags: string[]
  method: string  // 'ai' or 'rule_based'
}

export interface SourceSuggestion {
  name: string
  url: string
  type: string
  description: string
}

export interface DiscoverSourcesResult {
  topic: string
  suggestions: SourceSuggestion[]
}

// SSE event shape from backend
export interface SSEEvent {
  type: 'delta' | 'done' | 'error'
  content?: string
}

export const assistantApi = {
  // Streaming chat — uses fetch() with ReadableStream (NOT EventSource, because we need POST)
  async chatStream(
    messages: ChatMessage[],
    onDelta: (text: string) => void,
    onDone: () => void,
    onError: (error: string) => void,
    signal?: AbortSignal
  ): Promise<void> {
    const token = localStorage.getItem('access_token')
    const response = await fetch('/api/v1/assistant/chat-rag', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ messages, stream: true }),
      signal,
    })

    if (!response.ok) {
      onError(`HTTP ${response.status}`)
      return
    }

    const reader = response.body?.getReader()
    if (!reader) {
      onError('No response body')
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const event: SSEEvent = JSON.parse(line.slice(6))
          if (event.type === 'delta' && event.content) {
            onDelta(event.content)
          } else if (event.type === 'done') {
            onDone()
          } else if (event.type === 'error') {
            onError(event.content || 'Unknown error')
          }
        } catch {
          // skip non-JSON lines
        }
      }
    }
  },

  // Non-streaming chat fallback
  async chat(messages: ChatMessage[]): Promise<ApiResponse<{ reply: string }>> {
    const response = await apiClient.post<ApiResponse<{ reply: string }>>('/assistant/chat-rag', {
      messages,
      stream: false,
    })
    return response.data
  },

  async summarize(newsId: string): Promise<ApiResponse<SummarizeResult>> {
    const response = await apiClient.post<ApiResponse<SummarizeResult>>('/assistant/summarize', {
      news_id: newsId,
    })
    return response.data
  },

  async classify(newsId: string): Promise<ApiResponse<ClassifyResult>> {
    const response = await apiClient.post<ApiResponse<ClassifyResult>>('/assistant/classify', {
      news_id: newsId,
    })
    return response.data
  },

  async discoverSources(topic: string): Promise<ApiResponse<DiscoverSourcesResult>> {
    const response = await apiClient.post<ApiResponse<DiscoverSourcesResult>>('/assistant/discover-sources', {
      topic,
    })
    return response.data
  },
}

export default assistantApi
