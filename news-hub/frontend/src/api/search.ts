import apiClient from './client'
import type { ApiResponse } from './client'

export interface SearchResultItem {
  id: string
  title: string
  url: string
  description?: string
  image_url?: string
  source_name: string
  source_id: string
  published_at?: string
  crawled_at: string
  tags: string[]
  is_read: boolean
  is_starred: boolean
  score: number
  highlights: Record<string, string[]>
}

export interface SearchResponse {
  query: string
  total: number
  results: SearchResultItem[]
  took_ms: number
  search_type: string
}

export interface SuggestResponse {
  prefix: string
  suggestions: string[]
}

export interface SearchStatus {
  elasticsearch_available: boolean
  embedding_available: boolean
  embedding_model?: string
}

export type SearchType = 'keyword' | 'semantic' | 'hybrid'

export interface SearchParams {
  q: string
  search_type?: SearchType
  source_ids?: string
  tags?: string
  is_starred?: boolean
  start_date?: string
  end_date?: string
  page?: number
  page_size?: number
}

export const searchApi = {
  /**
   * Search news items
   */
  async search(params: SearchParams): Promise<ApiResponse<SearchResponse>> {
    const response = await apiClient.get<ApiResponse<SearchResponse>>('/search', { params })
    return response.data
  },

  /**
   * Get autocomplete suggestions
   */
  async suggest(q: string, size = 5): Promise<ApiResponse<SuggestResponse>> {
    const response = await apiClient.get<ApiResponse<SuggestResponse>>('/search/suggest', {
      params: { q, size }
    })
    return response.data
  },

  /**
   * Get search system status
   */
  async status(): Promise<ApiResponse<SearchStatus>> {
    const response = await apiClient.get<ApiResponse<SearchStatus>>('/search/status')
    return response.data
  },

  /**
   * Reindex all news for current user
   */
  async reindex(): Promise<ApiResponse<{ indexed: number; total?: number }>> {
    const response = await apiClient.post<ApiResponse<{ indexed: number; total?: number }>>('/search/reindex')
    return response.data
  },
}

export default searchApi
