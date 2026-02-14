import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { sourceApi, type SourceResponse, type SourceCreate, type SourceUpdate, type SourceStatus } from '@/api'

export const useSourceStore = defineStore('sources', () => {
  // State
  const sources = ref<SourceResponse[]>([])
  const currentSource = ref<SourceResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Getters
  const sourceCount = computed(() => sources.value.length)
  const activeSources = computed(() => sources.value.filter(s => s.status === 'active'))
  const errorSources = computed(() => sources.value.filter(s => s.status === 'error'))

  // Actions
  async function fetchSources(params?: { status?: SourceStatus; tag?: string }) {
    loading.value = true
    error.value = null

    try {
      const response = await sourceApi.list(params)
      sources.value = response.data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch sources'
    } finally {
      loading.value = false
    }
  }

  async function fetchSource(id: string) {
    loading.value = true
    error.value = null

    try {
      const response = await sourceApi.get(id)
      currentSource.value = response.data
      return response.data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to fetch source'
      return null
    } finally {
      loading.value = false
    }
  }

  async function createSource(data: SourceCreate): Promise<SourceResponse | null> {
    loading.value = true
    error.value = null

    try {
      const response = await sourceApi.create(data)
      sources.value.unshift(response.data)
      return response.data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to create source'
      return null
    } finally {
      loading.value = false
    }
  }

  async function updateSource(id: string, data: SourceUpdate): Promise<SourceResponse | null> {
    loading.value = true
    error.value = null

    try {
      const response = await sourceApi.update(id, data)
      const index = sources.value.findIndex(s => s.id === id)
      if (index !== -1) {
        sources.value[index] = response.data
      }
      if (currentSource.value?.id === id) {
        currentSource.value = response.data
      }
      return response.data
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to update source'
      return null
    } finally {
      loading.value = false
    }
  }

  async function deleteSource(id: string): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      await sourceApi.delete(id)
      sources.value = sources.value.filter(s => s.id !== id)
      if (currentSource.value?.id === id) {
        currentSource.value = null
      }
      return true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to delete source'
      return false
    } finally {
      loading.value = false
    }
  }

  async function refreshSource(id: string): Promise<boolean> {
    try {
      await sourceApi.refresh(id)
      // Update status to pending
      const source = sources.value.find(s => s.id === id)
      if (source) {
        source.status = 'pending'
      }
      return true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Failed to trigger refresh'
      return false
    }
  }

  function clearError() {
    error.value = null
  }

  return {
    // State
    sources,
    currentSource,
    loading,
    error,
    // Getters
    sourceCount,
    activeSources,
    errorSources,
    // Actions
    fetchSources,
    fetchSource,
    createSource,
    updateSource,
    deleteSource,
    refreshSource,
    clearError
  }
})
