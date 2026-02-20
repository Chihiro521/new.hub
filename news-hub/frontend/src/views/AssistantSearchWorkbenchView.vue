<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  assistantApi,
  type AugmentedSearchResultItem,
  type ExternalSearchOptions,
  type ExternalSearchStatus,
  type IngestJobStatus,
} from '@/api/assistant'

const loading = ref(false)
const error = ref('')
const options = ref<ExternalSearchOptions | null>(null)
const providerStatus = ref<ExternalSearchStatus | null>(null)

const query = ref('')
const provider = ref<'auto' | 'searxng' | 'tavily'>('auto')
const timeRange = ref('')
const language = ref('')
const maxResults = ref(10)
const persistMode = ref<'snippet' | 'enriched'>('enriched')

const searchSummary = ref('')
const results = ref<AugmentedSearchResultItem[]>([])
const sessionId = ref('')
const providerUsed = ref('')
const fallbackUsed = ref(false)
const selectedUrls = ref<string[]>([])

const ingestJob = ref<IngestJobStatus | null>(null)
const pollingTimer = ref<number | null>(null)

const availableProviders = computed(() => options.value?.providers ?? [])
const selectedCount = computed(() => selectedUrls.value.length)

async function loadOptions() {
  try {
    const response = await assistantApi.getExternalSearchOptions()
    options.value = response.data
    const defaultProvider = response.data?.default_provider
    if (defaultProvider === 'auto' || defaultProvider === 'searxng' || defaultProvider === 'tavily') {
      provider.value = defaultProvider
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '加载外部搜索配置失败'
  }
}

async function loadProviderStatus() {
  try {
    const response = await assistantApi.getExternalSearchStatus()
    providerStatus.value = response.data
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '加载外部搜索状态失败'
  }
}

async function runSearch() {
  if (!query.value.trim()) return
  loading.value = true
  error.value = ''
  searchSummary.value = ''
  results.value = []
  selectedUrls.value = []
  ingestJob.value = null

  try {
    const response = await assistantApi.augmentedSearch({
      query: query.value.trim(),
      include_external: true,
      persist_mode: 'none',
      external_provider: provider.value,
      max_external_results: maxResults.value,
      time_range: timeRange.value || undefined,
      language: language.value || undefined,
    })

    const payload = response.data
    if (!payload) return
    searchSummary.value = payload.summary || ''
    sessionId.value = payload.search_session_id || ''
    providerUsed.value = payload.provider_used || ''
    fallbackUsed.value = payload.fallback_used || false
    results.value = payload.results.filter(item => item.origin === 'external')
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '搜索失败'
  } finally {
    loading.value = false
  }
}

function toggleSelection(url: string, checked: boolean) {
  if (checked) {
    if (!selectedUrls.value.includes(url)) {
      selectedUrls.value.push(url)
    }
    return
  }
  selectedUrls.value = selectedUrls.value.filter(item => item !== url)
}

function onItemCheck(url: string, event: Event) {
  const target = event.target as HTMLInputElement | null
  toggleSelection(url, Boolean(target?.checked))
}

async function queueIngest() {
  if (!sessionId.value) {
    error.value = '当前搜索没有可入库会话，请先执行搜索'
    return
  }
  if (selectedUrls.value.length === 0) {
    error.value = '请至少勾选一条结果'
    return
  }

  loading.value = true
  error.value = ''
  try {
    const response = await assistantApi.queueSearchIngest({
      session_id: sessionId.value,
      selected_urls: selectedUrls.value,
      persist_mode: persistMode.value,
    })
    const jobId = response.data?.job_id
    if (jobId) {
      await refreshJob(jobId)
      startPolling(jobId)
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '提交入库任务失败'
  } finally {
    loading.value = false
  }
}

async function refreshJob(jobId: string) {
  try {
    const response = await assistantApi.getIngestJob(jobId)
    ingestJob.value = response.data ?? null
    if (!ingestJob.value) return
    if (ingestJob.value.status === 'completed' || ingestJob.value.status === 'failed') {
      stopPolling()
    }
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '获取任务状态失败'
    stopPolling()
  }
}

function startPolling(jobId: string) {
  stopPolling()
  pollingTimer.value = window.setInterval(() => {
    void refreshJob(jobId)
  }, 2000)
}

function stopPolling() {
  if (pollingTimer.value !== null) {
    window.clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

onMounted(() => {
  void loadOptions()
  void loadProviderStatus()
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<template>
  <div class="workbench-page">
    <main class="main-content">
      <section class="panel glass">
        <div class="search-form">
          <input
            v-model="query"
            class="query-input"
            placeholder="输入主题，例如：AI Agent 最新进展"
            :disabled="loading"
          />
          <select v-model="provider" class="select-input" :disabled="loading">
            <option value="auto">auto</option>
            <option value="searxng">searxng</option>
            <option value="tavily">tavily</option>
          </select>
          <input v-model="timeRange" class="text-input" placeholder="time_range: day/week/month/year" :disabled="loading" />
          <input v-model="language" class="text-input" placeholder="language: zh-CN / en-US" :disabled="loading" />
          <input v-model.number="maxResults" class="num-input" type="number" min="1" max="50" :disabled="loading" />
          <button class="action-btn" @click="runSearch" :disabled="loading || !query.trim()">执行外搜</button>
        </div>

        <div class="provider-status" v-if="availableProviders.length">
          <span
            v-for="item in availableProviders"
            :key="item.name"
            class="provider-chip"
            :class="{ down: !item.available }"
          >
            {{ item.name }}: {{ item.available ? 'up' : 'down' }}
          </span>
        </div>
        <p v-if="providerStatus" class="meta-line">
          healthy providers: {{ providerStatus.healthy_provider_count }}
        </p>

        <p v-if="providerUsed" class="meta-line">
          provider: {{ providerUsed }} <span v-if="fallbackUsed">(fallback used)</span>
        </p>
        <p v-if="searchSummary" class="summary-line">{{ searchSummary }}</p>
        <p v-if="error" class="error-line">{{ error }}</p>
      </section>

      <section class="panel glass">
        <div class="toolbar">
          <h2>外部结果 ({{ results.length }})</h2>
          <div class="toolbar-actions">
            <label class="mode-label">
              入库模式
              <select v-model="persistMode" class="select-input" :disabled="loading">
                <option value="snippet">snippet</option>
                <option value="enriched">enriched</option>
              </select>
            </label>
            <button class="action-btn" @click="queueIngest" :disabled="loading || selectedCount === 0">
              入库选中项 ({{ selectedCount }})
            </button>
          </div>
        </div>

        <div class="results-list">
          <label v-for="item in results" :key="item.url" class="result-card">
            <input
              type="checkbox"
              :checked="selectedUrls.includes(item.url)"
              @change="onItemCheck(item.url, $event)"
            />
            <div class="result-content">
              <a :href="item.url" target="_blank" rel="noopener noreferrer" class="result-title">{{ item.title }}</a>
              <p class="result-desc">{{ item.description }}</p>
              <p class="result-meta">
                {{ item.source_name }} | {{ item.provider || 'external' }} | score: {{ item.score.toFixed(3) }}
              </p>
            </div>
          </label>
        </div>
      </section>

      <section class="panel glass" v-if="ingestJob">
        <h2>入库任务</h2>
        <p>job_id: {{ ingestJob.job_id }}</p>
        <p>status: {{ ingestJob.status }}</p>
        <p>progress: {{ ingestJob.processed_items }} / {{ ingestJob.total_items }}</p>
        <p>stored: {{ ingestJob.stored_items }} | failed: {{ ingestJob.failed_items }}</p>
        <p v-if="ingestJob.error_message" class="error-line">{{ ingestJob.error_message }}</p>
      </section>
    </main>
  </div>
</template>

<style scoped>
.workbench-page {
  background: var(--color-bg-canvas);
}

.main-content {
  max-width: 1200px;
  margin: 0 auto;
  padding: 1rem;
  display: grid;
  gap: 1rem;
}

.panel {
  border: 1px solid var(--color-neutral-200);
  border-radius: var(--radius-xl);
  padding: 1rem;
  background: rgba(255, 255, 255, 0.7);
}

.search-form {
  display: grid;
  grid-template-columns: 2fr 120px 180px 180px 100px 140px;
  gap: 0.5rem;
}

.query-input,
.text-input,
.num-input,
.select-input {
  border: 1px solid var(--color-neutral-300);
  border-radius: 8px;
  padding: 0.55rem 0.65rem;
  font: inherit;
  background: white;
}

.action-btn {
  border: none;
  border-radius: 8px;
  padding: 0.55rem 0.9rem;
  font-weight: 600;
  background: var(--color-primary-600);
  color: white;
  cursor: pointer;
}

.action-btn:disabled {
  background: var(--color-neutral-300);
  cursor: not-allowed;
}

.provider-status {
  margin-top: 0.75rem;
  display: flex;
  gap: 0.5rem;
}

.provider-chip {
  font-size: 0.82rem;
  border: 1px solid var(--color-success-300);
  color: var(--color-success-700);
  border-radius: 999px;
  padding: 0.2rem 0.6rem;
  background: var(--color-success-50);
}

.provider-chip.down {
  border-color: var(--color-error-300);
  color: var(--color-error-700);
  background: var(--color-error-50);
}

.meta-line,
.summary-line,
.error-line {
  margin-top: 0.75rem;
}

.error-line {
  color: var(--color-error-700);
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.mode-label {
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.results-list {
  display: grid;
  gap: 0.75rem;
}

.result-card {
  display: grid;
  grid-template-columns: 24px 1fr;
  gap: 0.65rem;
  border: 1px solid var(--color-neutral-200);
  border-radius: 10px;
  padding: 0.7rem 0.8rem;
  background: rgba(255, 255, 255, 0.9);
}

.result-title {
  font-weight: 600;
  color: var(--color-primary-700);
  text-decoration: none;
}

.result-title:hover {
  text-decoration: underline;
}

.result-desc {
  margin-top: 0.35rem;
  color: var(--color-neutral-700);
}

.result-meta {
  margin-top: 0.35rem;
  font-size: 0.82rem;
  color: var(--color-neutral-500);
}

@media (max-width: 1024px) {
  .search-form {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 640px) {
  .search-form {
    grid-template-columns: 1fr;
  }

  .toolbar {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
