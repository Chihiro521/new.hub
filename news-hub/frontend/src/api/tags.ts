import apiClient from './client'
import type { ApiResponse } from './client'

// Types
export type MatchMode = 'any' | 'all'

export interface TagRuleCreate {
  tag_name: string
  keywords: string[]
  match_mode?: MatchMode
  case_sensitive?: boolean
  match_title?: boolean
  match_description?: boolean
  match_content?: boolean
  priority?: number
}

export interface TagRuleUpdate {
  tag_name?: string
  keywords?: string[]
  match_mode?: MatchMode
  case_sensitive?: boolean
  match_title?: boolean
  match_description?: boolean
  match_content?: boolean
  priority?: number
  is_active?: boolean
}

export interface TagRuleResponse {
  id: string
  user_id: string
  tag_name: string
  keywords: string[]
  match_mode: MatchMode
  case_sensitive: boolean
  match_title: boolean
  match_description: boolean
  match_content: boolean
  priority: number
  is_active: boolean
  match_count: number
  created_at: string
}

export interface TagCount {
  tag_name: string
  count: number
}

export interface TagStats {
  rules_count: number
  unique_tags: number
  total_tagged_items: number
}

// Tags API
export const tagApi = {
  // === Tag Rules CRUD ===

  /**
   * Create a new tag rule
   */
  async createRule(data: TagRuleCreate): Promise<ApiResponse<TagRuleResponse>> {
    const response = await apiClient.post<ApiResponse<TagRuleResponse>>('/tags/rules', data)
    return response.data
  },

  /**
   * List tag rules
   */
  async listRules(params?: {
    is_active?: boolean
    skip?: number
    limit?: number
  }): Promise<ApiResponse<TagRuleResponse[]>> {
    const response = await apiClient.get<ApiResponse<TagRuleResponse[]>>('/tags/rules', { params })
    return response.data
  },

  /**
   * Get a tag rule by ID
   */
  async getRule(id: string): Promise<ApiResponse<TagRuleResponse>> {
    const response = await apiClient.get<ApiResponse<TagRuleResponse>>(`/tags/rules/${id}`)
    return response.data
  },

  /**
   * Update a tag rule
   */
  async updateRule(id: string, data: TagRuleUpdate): Promise<ApiResponse<TagRuleResponse>> {
    const response = await apiClient.patch<ApiResponse<TagRuleResponse>>(`/tags/rules/${id}`, data)
    return response.data
  },

  /**
   * Delete a tag rule
   */
  async deleteRule(id: string): Promise<ApiResponse<null>> {
    const response = await apiClient.delete<ApiResponse<null>>(`/tags/rules/${id}`)
    return response.data
  },

  // === Tag Queries ===

  /**
   * Get all tags used by the current user with counts
   */
  async getUserTags(): Promise<ApiResponse<TagCount[]>> {
    const response = await apiClient.get<ApiResponse<TagCount[]>>('/tags')
    return response.data
  },

  /**
   * Get tag statistics
   */
  async getStats(): Promise<ApiResponse<TagStats>> {
    const response = await apiClient.get<ApiResponse<TagStats>>('/tags/stats')
    return response.data
  },

  // === Utilities ===

  /**
   * Extract keywords from text
   */
  async extractKeywords(
    text: string,
    topK: number = 10,
    method: string = 'tfidf'
  ): Promise<ApiResponse<string[]>> {
    const response = await apiClient.post<ApiResponse<string[]>>(
      '/tags/extract-keywords',
      null,
      { params: { text, top_k: topK, method } }
    )
    return response.data
  },

  /**
   * Re-apply tag rules to existing news items
   */
  async retagNews(params?: {
    source_id?: string
    limit?: number
  }): Promise<ApiResponse<{ retagged: number; total_processed: number }>> {
    const response = await apiClient.post<ApiResponse<{ retagged: number; total_processed: number }>>(
      '/tags/retag-news',
      null,
      { params }
    )
    return response.data
  }
}
