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

export interface AugmentedSearchRequest {
  query: string
  include_external?: boolean
  persist_external?: boolean
  persist_mode?: 'none' | 'snippet' | 'enriched'
  external_provider?: 'auto' | 'searxng' | 'tavily'
  max_external_results?: number
  time_range?: string
  language?: string
  engines?: string[]
}

export interface AugmentedSearchResultItem {
  title: string
  url: string
  description: string
  source_name: string
  score: number
  origin: 'internal' | 'external'
  news_id?: string
  provider?: string
  engine?: string
}

export interface AugmentedSearchResult {
  query: string
  summary: string
  results: AugmentedSearchResultItem[]
  internal_count: number
  external_count: number
  provider_used?: string
  fallback_used: boolean
  search_session_id?: string
}

export interface ExternalSearchProviderOption {
  name: string
  available: boolean
  supports: Record<string, boolean>
  engines: string[]
  languages: string[]
  time_ranges: string[]
}

export interface ExternalSearchOptions {
  default_provider: string
  fallback_provider: string
  providers: ExternalSearchProviderOption[]
}

export interface SearchIngestRequest {
  session_id: string
  selected_urls: string[]
  persist_mode: 'snippet' | 'enriched'
}

export interface SearchIngestResponse {
  job_id: string
  status: string
  queued_count: number
  persist_mode: string
}

export interface IngestJobStatus {
  job_id: string
  status: string
  session_id: string
  persist_mode: string
  total_items: number
  processed_items: number
  stored_items: number
  failed_items: number
  retry_count: number
  average_quality_score: number
  error_message?: string
  created_at: string
  updated_at: string
}

export interface ExternalSearchStatusProviderItem {
  provider: string
  available: boolean
  healthy: boolean
  latency_ms: number
  message: string
}

export interface ExternalSearchStatus {
  default_provider: string
  fallback_provider: string
  healthy_provider_count: number
  providers: ExternalSearchStatusProviderItem[]
}

// --- External Search (pure) ---

export interface ExternalSearchRequest {
  query: string
  provider?: 'auto' | 'searxng' | 'tavily'
  max_results?: number
  time_range?: string
  language?: string
}

export interface ExternalSearchResultItem {
  title: string
  url: string
  description: string
  source_name: string
  score: number
  provider?: string
  engine?: string
  published_at?: string
}

export interface ExternalSearchResult {
  query: string
  results: ExternalSearchResultItem[]
  total: number
  provider_used?: string
}

// --- Ingest One ---

export interface IngestOneRequest {
  url: string
  title?: string
  description?: string
  provider?: string
}

export interface IngestOneResult {
  success: boolean
  news_id?: string
  quality_score: number
  message: string
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

  async augmentedSearch(
    payload: AugmentedSearchRequest
  ): Promise<ApiResponse<AugmentedSearchResult>> {
    const response = await apiClient.post<ApiResponse<AugmentedSearchResult>>(
      '/assistant/search',
      payload
    )
    return response.data
  },

  async getExternalSearchOptions(): Promise<ApiResponse<ExternalSearchOptions>> {
    const response = await apiClient.get<ApiResponse<ExternalSearchOptions>>(
      '/assistant/external-search/options'
    )
    return response.data
  },

  async getExternalSearchStatus(): Promise<ApiResponse<ExternalSearchStatus>> {
    const response = await apiClient.get<ApiResponse<ExternalSearchStatus>>(
      '/assistant/external-search/status'
    )
    return response.data
  },

  async queueSearchIngest(
    payload: SearchIngestRequest
  ): Promise<ApiResponse<SearchIngestResponse>> {
    const response = await apiClient.post<ApiResponse<SearchIngestResponse>>(
      '/assistant/search/ingest',
      payload
    )
    return response.data
  },

  async getIngestJob(jobId: string): Promise<ApiResponse<IngestJobStatus>> {
    const response = await apiClient.get<ApiResponse<IngestJobStatus>>(
      `/assistant/ingest-jobs/${jobId}`
    )
    return response.data
  },

  async externalSearch(
    payload: ExternalSearchRequest
  ): Promise<ApiResponse<ExternalSearchResult>> {
    const response = await apiClient.post<ApiResponse<ExternalSearchResult>>(
      '/assistant/external-search',
      payload
    )
    return response.data
  },

  async ingestOne(
    payload: IngestOneRequest
  ): Promise<ApiResponse<IngestOneResult>> {
    const response = await apiClient.post<ApiResponse<IngestOneResult>>(
      '/assistant/ingest-one',
      payload
    )
    return response.data
  },
}

export default assistantApi
