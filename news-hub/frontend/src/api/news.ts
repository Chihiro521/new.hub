import apiClient from './client'
import type { ApiResponse } from './client'

export interface NewsMetadata {
  author?: string
  hot_score: number
  view_count: number
  like_count: number
  comment_count: number
  language: string
  extra: Record<string, unknown>
}

export interface NewsItem {
  id: string
  source_id: string
  source_name: string
  source_type: string
  title: string
  url: string
  description?: string
  content?: string
  image_url?: string
  published_at?: string
  tags: string[]
  metadata: NewsMetadata
  is_read: boolean
  is_starred: boolean
  crawled_at: string
  proxied_image_url?: string
}

export interface NewsItemBrief {
  id: string
  title: string
  url: string
  description?: string
  image_url?: string
  source_name: string
  published_at?: string
  tags: string[]
  is_read: boolean
  is_starred: boolean
}

export interface NewsListParams {
  source_id?: string
  tag?: string
  is_starred?: boolean
  is_read?: boolean
  start_date?: string
  end_date?: string
  skip?: number
  limit?: number
  sort_by?: 'crawled_at' | 'published_at'
}

export interface NewsStats {
  total: number
  unread: number
  starred: number
}

export interface NewsStateUpdate {
  is_read?: boolean
  is_starred?: boolean
}

export const newsApi = {
  /**
   * List news items with optional filters
   */
  async list(params?: NewsListParams): Promise<ApiResponse<NewsItemBrief[]>> {
    const response = await apiClient.get<ApiResponse<NewsItemBrief[]>>('/news', { params })
    return response.data
  },

  /**
   * Get count of news items
   */
  async count(params?: Pick<NewsListParams, 'source_id' | 'is_starred' | 'is_read'>): Promise<ApiResponse<{ count: number }>> {
    const response = await apiClient.get<ApiResponse<{ count: number }>>('/news/count', { params })
    return response.data
  },

  /**
   * Get news statistics
   */
  async stats(): Promise<ApiResponse<NewsStats>> {
    const response = await apiClient.get<ApiResponse<NewsStats>>('/news/stats')
    return response.data
  },

  /**
   * Get a single news item by ID
   */
  async get(newsId: string): Promise<ApiResponse<NewsItem>> {
    const response = await apiClient.get<ApiResponse<NewsItem>>(`/news/${newsId}`)
    return response.data
  },

  /**
   * Update news item state (read/starred)
   */
  async updateState(newsId: string, update: NewsStateUpdate): Promise<ApiResponse<NewsItemBrief>> {
    const response = await apiClient.patch<ApiResponse<NewsItemBrief>>(`/news/${newsId}`, update)
    return response.data
  },

  /**
   * Mark all news as read
   */
  async markAllRead(sourceId?: string): Promise<ApiResponse<{ marked_count: number }>> {
    const response = await apiClient.post<ApiResponse<{ marked_count: number }>>(
      '/news/mark-all-read',
      null,
      { params: sourceId ? { source_id: sourceId } : undefined }
    )
    return response.data
  },

  /**
   * Delete a news item
   */
  async delete(newsId: string): Promise<ApiResponse<null>> {
    const response = await apiClient.delete<ApiResponse<null>>(`/news/${newsId}`)
    return response.data
  },
}

export default newsApi
