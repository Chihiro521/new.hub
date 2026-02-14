import apiClient from './client'
import type { ApiResponse } from './client'

// Types
export type SourceType = 'rss' | 'api' | 'html'
export type SourceStatus = 'active' | 'paused' | 'error' | 'pending'

export interface ParserConfigAPI {
  list_path: string
  fields: Record<string, string>
  pagination?: {
    type: 'offset' | 'cursor'
    param: string
    step: number
  }
  headers?: Record<string, string>
}

export interface ParserConfigHTML {
  list_selector: string
  link_selector: string
  fields?: Record<string, string>
  use_playwright?: boolean
  wait_for?: string
}

export interface ParserConfig {
  mode: SourceType
  api?: ParserConfigAPI
  html?: ParserConfigHTML
}

export interface SourceCreate {
  name: string
  url: string
  source_type: SourceType
  description?: string
  logo_url?: string
  homepage?: string
  tags?: string[]
  parser_config?: ParserConfig
  refresh_interval_minutes?: number
}

export interface SourceUpdate {
  name?: string
  description?: string
  logo_url?: string
  parser_config?: ParserConfig
  refresh_interval_minutes?: number
  status?: SourceStatus
  tags?: string[]
}

export interface SourceResponse {
  id: string
  user_id: string
  name: string
  url: string
  source_type: SourceType
  description: string | null
  logo_url: string | null
  homepage: string | null
  tags: string[]
  status: SourceStatus
  parser_config: ParserConfig | null
  refresh_interval_minutes: number
  last_fetched_at: string | null
  last_error: string | null
  fetch_count: number
  item_count: number
  created_at: string
}

export interface SourceDetectRequest {
  url: string
}

export interface SourceDetectResponse {
  detected_type: SourceType
  suggested_name: string | null
  suggested_config: ParserConfig | null
  preview_items: Array<Record<string, unknown>>
  confidence: number
}

// Source API
export const sourceApi = {
  /**
   * List all sources
   */
  async list(params?: {
    status?: SourceStatus
    tag?: string
    skip?: number
    limit?: number
  }): Promise<ApiResponse<SourceResponse[]>> {
    const response = await apiClient.get<ApiResponse<SourceResponse[]>>('/sources', { params })
    return response.data
  },

  /**
   * Get a source by ID
   */
  async get(id: string): Promise<ApiResponse<SourceResponse>> {
    const response = await apiClient.get<ApiResponse<SourceResponse>>(`/sources/${id}`)
    return response.data
  },

  /**
   * Create a new source
   */
  async create(data: SourceCreate): Promise<ApiResponse<SourceResponse>> {
    const response = await apiClient.post<ApiResponse<SourceResponse>>('/sources', data)
    return response.data
  },

  /**
   * Update a source
   */
  async update(id: string, data: SourceUpdate): Promise<ApiResponse<SourceResponse>> {
    const response = await apiClient.patch<ApiResponse<SourceResponse>>(`/sources/${id}`, data)
    return response.data
  },

  /**
   * Delete a source
   */
  async delete(id: string): Promise<ApiResponse<null>> {
    const response = await apiClient.delete<ApiResponse<null>>(`/sources/${id}`)
    return response.data
  },

  /**
   * Detect source type from URL
   */
  async detect(url: string): Promise<ApiResponse<SourceDetectResponse>> {
    const response = await apiClient.post<ApiResponse<SourceDetectResponse>>('/sources/detect', { url })
    return response.data
  },

  /**
   * Trigger manual refresh
   */
  async refresh(id: string): Promise<ApiResponse<null>> {
    const response = await apiClient.post<ApiResponse<null>>(`/sources/${id}/refresh`)
    return response.data
  }
}
