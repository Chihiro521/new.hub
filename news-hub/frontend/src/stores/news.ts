import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { newsApi, type NewsItemBrief, type NewsItem, type NewsStats, type NewsListParams } from '@/api/news'

export const useNewsStore = defineStore('news', () => {
  // State
  const newsList = ref<NewsItemBrief[]>([])
  const currentNews = ref<NewsItem | null>(null)
  const stats = ref<NewsStats>({ total: 0, unread: 0, starred: 0 })
  const loading = ref(false)
  const error = ref<string | null>(null)
  const hasMore = ref(true)
  const currentFilters = ref<NewsListParams>({})

  // Getters
  const unreadCount = computed(() => stats.value.unread)
  const starredCount = computed(() => stats.value.starred)
  const totalCount = computed(() => stats.value.total)
  const unreadNews = computed(() => newsList.value.filter(n => !n.is_read))
  const starredNews = computed(() => newsList.value.filter(n => n.is_starred))

  // Actions
  async function fetchNews(params?: NewsListParams, append = false) {
    loading.value = true
    error.value = null

    try {
      currentFilters.value = params || {}
      const result = await newsApi.list({
        limit: 20,
        skip: append ? newsList.value.length : 0,
        ...params,
      })

      if (result.code === 200) {
        if (append) {
          newsList.value = [...newsList.value, ...result.data]
        } else {
          newsList.value = result.data
        }
        hasMore.value = result.data.length >= 20
      } else {
        error.value = result.message
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to fetch news'
      error.value = message
    } finally {
      loading.value = false
    }
  }

  async function loadMore() {
    if (!hasMore.value || loading.value) return
    await fetchNews(currentFilters.value, true)
  }

  async function fetchStats() {
    try {
      const result = await newsApi.stats()
      if (result.code === 200) {
        stats.value = result.data
      }
    } catch {
      // Silently fail - stats are not critical
    }
  }

  async function fetchNewsItem(newsId: string) {
    loading.value = true
    error.value = null

    try {
      const result = await newsApi.get(newsId)
      if (result.code === 200) {
        currentNews.value = result.data
      } else {
        error.value = result.message
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to fetch news item'
      error.value = message
    } finally {
      loading.value = false
    }
  }

  async function markAsRead(newsId: string) {
    try {
      const result = await newsApi.updateState(newsId, { is_read: true })
      if (result.code === 200) {
        // Update in list
        const index = newsList.value.findIndex(n => n.id === newsId)
        if (index !== -1) {
          newsList.value[index] = result.data
        }
        // Update current if viewing
        if (currentNews.value?.id === newsId) {
          currentNews.value.is_read = true
        }
        // Update stats
        if (stats.value.unread > 0) {
          stats.value.unread--
        }
      }
    } catch {
      // Silently fail
    }
  }

  async function toggleStar(newsId: string) {
    const item = newsList.value.find(n => n.id === newsId)
    if (!item) return

    const newState = !item.is_starred

    try {
      const result = await newsApi.updateState(newsId, { is_starred: newState })
      if (result.code === 200) {
        // Update in list
        const index = newsList.value.findIndex(n => n.id === newsId)
        if (index !== -1) {
          newsList.value[index] = result.data
        }
        // Update current if viewing
        if (currentNews.value?.id === newsId) {
          currentNews.value.is_starred = newState
        }
        // Update stats
        stats.value.starred += newState ? 1 : -1
      }
    } catch {
      // Silently fail
    }
  }

  async function markAllAsRead(sourceId?: string) {
    try {
      const result = await newsApi.markAllRead(sourceId)
      if (result.code === 200) {
        // Update all items in current list
        newsList.value = newsList.value.map(n => ({
          ...n,
          is_read: sourceId ? (n.source_name === sourceId || n.is_read) : true
        }))
        // Refresh stats
        await fetchStats()
      }
    } catch {
      // Silently fail
    }
  }

  function clearError() {
    error.value = null
  }

  function reset() {
    newsList.value = []
    currentNews.value = null
    stats.value = { total: 0, unread: 0, starred: 0 }
    hasMore.value = true
    currentFilters.value = {}
  }

  return {
    // State
    newsList,
    currentNews,
    stats,
    loading,
    error,
    hasMore,
    currentFilters,

    // Getters
    unreadCount,
    starredCount,
    totalCount,
    unreadNews,
    starredNews,

    // Actions
    fetchNews,
    loadMore,
    fetchStats,
    fetchNewsItem,
    markAsRead,
    toggleStar,
    markAllAsRead,
    clearError,
    reset,
  }
})
