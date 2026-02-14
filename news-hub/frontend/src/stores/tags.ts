import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { tagApi, type TagRuleResponse, type TagRuleCreate, type TagRuleUpdate, type TagCount, type TagStats } from '@/api/tags'

export const useTagStore = defineStore('tags', () => {
  // State
  const rules = ref<TagRuleResponse[]>([])
  const userTags = ref<TagCount[]>([])
  const stats = ref<TagStats | null>(null)
  const currentRule = ref<TagRuleResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Getters
  const rulesCount = computed(() => rules.value.length)
  const activeRules = computed(() => rules.value.filter(r => r.is_active))
  const topTags = computed(() => userTags.value.slice(0, 10))

  // Actions
  async function fetchRules(params?: { is_active?: boolean }) {
    loading.value = true
    error.value = null

    try {
      const response = await tagApi.listRules(params)
      rules.value = response.data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch tag rules'
    } finally {
      loading.value = false
    }
  }

  async function fetchRule(id: string) {
    loading.value = true
    error.value = null

    try {
      const response = await tagApi.getRule(id)
      currentRule.value = response.data
      return response.data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch tag rule'
      return null
    } finally {
      loading.value = false
    }
  }

  async function createRule(data: TagRuleCreate): Promise<TagRuleResponse | null> {
    loading.value = true
    error.value = null

    try {
      const response = await tagApi.createRule(data)
      rules.value.unshift(response.data)
      return response.data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to create tag rule'
      return null
    } finally {
      loading.value = false
    }
  }

  async function updateRule(id: string, data: TagRuleUpdate): Promise<TagRuleResponse | null> {
    loading.value = true
    error.value = null

    try {
      const response = await tagApi.updateRule(id, data)
      const index = rules.value.findIndex(r => r.id === id)
      if (index !== -1) {
        rules.value[index] = response.data
      }
      if (currentRule.value?.id === id) {
        currentRule.value = response.data
      }
      return response.data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to update tag rule'
      return null
    } finally {
      loading.value = false
    }
  }

  async function deleteRule(id: string): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      await tagApi.deleteRule(id)
      rules.value = rules.value.filter(r => r.id !== id)
      if (currentRule.value?.id === id) {
        currentRule.value = null
      }
      return true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to delete tag rule'
      return false
    } finally {
      loading.value = false
    }
  }

  async function toggleRuleActive(id: string): Promise<boolean> {
    const rule = rules.value.find(r => r.id === id)
    if (!rule) return false

    const result = await updateRule(id, { is_active: !rule.is_active })
    return result !== null
  }

  async function fetchUserTags() {
    try {
      const response = await tagApi.getUserTags()
      userTags.value = response.data
    } catch (e) {
      console.error('Failed to fetch user tags:', e)
    }
  }

  async function fetchStats() {
    try {
      const response = await tagApi.getStats()
      stats.value = response.data
    } catch (e) {
      console.error('Failed to fetch tag stats:', e)
    }
  }

  async function extractKeywords(text: string, topK: number = 10): Promise<string[]> {
    try {
      const response = await tagApi.extractKeywords(text, topK)
      return response.data
    } catch (e) {
      console.error('Failed to extract keywords:', e)
      return []
    }
  }

  async function retagNews(sourceId?: string, limit: number = 100): Promise<{ retagged: number; total: number } | null> {
    loading.value = true
    error.value = null

    try {
      const response = await tagApi.retagNews({ source_id: sourceId, limit })
      return {
        retagged: response.data.retagged,
        total: response.data.total_processed
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to retag news'
      return null
    } finally {
      loading.value = false
    }
  }

  function clearError() {
    error.value = null
  }

  return {
    // State
    rules,
    userTags,
    stats,
    currentRule,
    loading,
    error,
    // Getters
    rulesCount,
    activeRules,
    topTags,
    // Actions
    fetchRules,
    fetchRule,
    createRule,
    updateRule,
    deleteRule,
    toggleRuleActive,
    fetchUserTags,
    fetchStats,
    extractKeywords,
    retagNews,
    clearError
  }
})
