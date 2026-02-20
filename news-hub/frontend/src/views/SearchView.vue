<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useRoute } from 'vue-router'
import { searchApi, type SearchResultItem, type SearchType } from '@/api/search'
import { assistantApi, type ExternalSearchResultItem } from '@/api/assistant'
import SearchBar from '@/components/SearchBar.vue'

const route = useRoute()

// --- Shared state ---
const searchQuery = ref('')
const activeTab = ref<'internal' | 'external'>('internal')

// --- Internal search state ---
const searchType = ref<SearchType>('hybrid')
const results = ref<SearchResultItem[]>([])
const totalResults = ref(0)
const currentPage = ref(1)
const isLoading = ref(false)
const searchTook = ref(0)
const error = ref<string | null>(null)
const pageSize = 20
const hasMore = computed(() => results.value.length < totalResults.value)

// --- External search state ---
const extResults = ref<ExternalSearchResultItem[]>([])
const extTotal = ref(0)
const extLoading = ref(false)
const extError = ref<string | null>(null)
const extProvider = ref<'auto' | 'searxng' | 'tavily'>('auto')
const extProviderUsed = ref('')

// Per-card ingest state: url -> status
const ingestStatus = ref<Record<string, 'idle' | 'ingesting' | 'success' | 'failed'>>({})

onMounted(() => {
  const q = route.query.q as string
  if (q) {
    searchQuery.value = q
    performSearch()
  }
})

watch(() => route.query.q, (newQ) => {
  if (newQ && newQ !== searchQuery.value) {
    searchQuery.value = newQ as string
    currentPage.value = 1
    performSearch()
  }
})

// --- Internal search ---
async function performSearch() {
  if (!searchQuery.value.trim()) return
  isLoading.value = true
  error.value = null
  try {
    const result = await searchApi.search({
      q: searchQuery.value,
      search_type: searchType.value,
      page: currentPage.value,
      page_size: pageSize,
    })
    if (result.code === 200) {
      if (currentPage.value === 1) {
        results.value = result.data.results
      } else {
        results.value = [...results.value, ...result.data.results]
      }
      totalResults.value = result.data.total
      searchTook.value = result.data.took_ms
    } else {
      error.value = result.message
    }
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : '搜索失败'
  } finally {
    isLoading.value = false
  }
}

// --- External search ---
async function performExternalSearch() {
  if (!searchQuery.value.trim()) return
  extLoading.value = true
  extError.value = null
  extResults.value = []
  ingestStatus.value = {}
  try {
    const result = await assistantApi.externalSearch({
      query: searchQuery.value,
      provider: extProvider.value,
      max_results: 20,
    })
    if (result.code === 200) {
      extResults.value = result.data.results
      extTotal.value = result.data.total
      extProviderUsed.value = result.data.provider_used || ''
    } else {
      extError.value = result.message
    }
  } catch (err: unknown) {
    extError.value = err instanceof Error ? err.message : '外部搜索失败'
  } finally {
    extLoading.value = false
  }
}

function handleSearch(query: string) {
  searchQuery.value = query
  currentPage.value = 1
  results.value = []
  if (activeTab.value === 'internal') {
    performSearch()
  } else {
    performExternalSearch()
  }
}

function handleSearchTypeChange() {
  currentPage.value = 1
  results.value = []
  performSearch()
}

function switchTab(tab: 'internal' | 'external') {
  activeTab.value = tab
  if (searchQuery.value.trim()) {
    if (tab === 'internal' && results.value.length === 0) {
      currentPage.value = 1
      performSearch()
    } else if (tab === 'external' && extResults.value.length === 0) {
      performExternalSearch()
    }
  }
}

async function loadMore() {
  if (isLoading.value || !hasMore.value) return
  currentPage.value++
  await performSearch()
}

async function handleIngest(item: ExternalSearchResultItem) {
  const url = item.url
  if (ingestStatus.value[url] === 'ingesting' || ingestStatus.value[url] === 'success') return
  ingestStatus.value[url] = 'ingesting'
  try {
    const result = await assistantApi.ingestOne({
      url: item.url,
      title: item.title,
      description: item.description,
      provider: item.provider || extProviderUsed.value || 'searxng',
    })
    if (result.code === 200 && result.data.success) {
      ingestStatus.value[url] = 'success'
    } else {
      ingestStatus.value[url] = 'failed'
    }
  } catch {
    ingestStatus.value[url] = 'failed'
  }
}

function openArticle(url: string) {
  window.open(url, '_blank')
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function highlightText(text: string, highlights: Record<string, string[]>, field: string): string {
  const fieldHighlights = highlights[field]
  if (fieldHighlights && fieldHighlights.length > 0) {
    return fieldHighlights[0]
  }
  return text
}
</script>

<template>
  <div class="search-page">
    <main class="main-content">
      <!-- Search Box -->
      <div class="search-section">
        <h2 class="search-title">搜索新闻</h2>
        <SearchBar
          v-model="searchQuery"
          placeholder="搜索文章..."
          @search="handleSearch"
        />

        <!-- Tab Switcher -->
        <div class="tab-bar">
          <button
            :class="['tab-btn', { active: activeTab === 'internal' }]"
            @click="switchTab('internal')"
          >站内搜索</button>
          <button
            :class="['tab-btn', { active: activeTab === 'external' }]"
            @click="switchTab('external')"
          >外部搜索</button>
        </div>

        <!-- Internal search options -->
        <div v-if="activeTab === 'internal'" class="search-options">
          <div class="option-group">
            <label>搜索模式：</label>
            <select v-model="searchType" @change="handleSearchTypeChange" class="input">
              <option value="hybrid">混合搜索（推荐）</option>
              <option value="keyword">仅关键词</option>
              <option value="semantic">仅语义</option>
            </select>
          </div>
        </div>
      </div>

      <!-- ========== Internal Tab ========== -->
      <template v-if="activeTab === 'internal'">
        <div v-if="totalResults > 0 || searchQuery" class="results-info">
          <span v-if="totalResults > 0">
            找到 <strong>{{ totalResults }}</strong> 条结果
            <span class="took-time">({{ searchTook }}ms)</span>
          </span>
          <span v-else-if="!isLoading && searchQuery">未找到"{{ searchQuery }}"的相关结果</span>
        </div>

        <div v-if="isLoading && results.length === 0" class="loading">
          <div class="spinner"></div>
          <span>搜索中...</span>
        </div>

        <div v-else-if="error" class="error-message card">
          {{ error }}
          <button @click="error = null">关闭</button>
        </div>

        <div v-else-if="results.length > 0" class="results-list">
          <article
            v-for="item in results"
            :key="item.id"
            class="result-card card"
            @click="openArticle(item.url)"
          >
            <div class="result-image" v-if="item.image_url">
              <img :src="item.image_url" :alt="item.title" loading="lazy" />
            </div>
            <div class="result-content">
              <div class="result-header">
                <span class="result-source">{{ item.source_name }}</span>
                <span class="result-date">{{ formatDate(item.published_at) }}</span>
                <span class="result-score">评分: {{ item.score.toFixed(2) }}</span>
              </div>
              <h3 class="result-title" v-html="highlightText(item.title, item.highlights, 'title')"></h3>
              <p v-if="item.description" class="result-description" v-html="highlightText(item.description, item.highlights, 'description')"></p>
              <div class="result-tags" v-if="item.tags.length > 0">
                <span v-for="tag in item.tags.slice(0, 3)" :key="tag" class="tag">{{ tag }}</span>
              </div>
            </div>
          </article>
          <div v-if="hasMore" class="load-more">
            <button class="btn-secondary" :disabled="isLoading" @click="loadMore">
              {{ isLoading ? '加载中...' : '加载更多' }}
            </button>
          </div>
        </div>

        <div v-else-if="!searchQuery" class="empty-state">
          <div class="empty-icon">&#x1F50D;</div>
          <h3>开始搜索</h3>
          <p>输入关键词或短语来查找新闻文章。</p>
          <div class="search-tips">
            <p><strong>提示：</strong></p>
            <ul>
              <li>使用<strong>混合搜索</strong>模式获得最佳结果</li>
              <li><strong>语义搜索</strong>能理解语义，不仅仅是关键词匹配</li>
              <li>试试自然语言查询，如"新能源汽车发展趋势"</li>
            </ul>
          </div>
        </div>
      </template>

      <!-- ========== External Tab ========== -->
      <template v-if="activeTab === 'external'">
        <div v-if="extTotal > 0" class="results-info">
          找到 <strong>{{ extTotal }}</strong> 条外部结果
          <span v-if="extProviderUsed" class="took-time">({{ extProviderUsed }})</span>
        </div>

        <div v-if="extLoading" class="loading">
          <div class="spinner"></div>
          <span>外部搜索中...</span>
        </div>

        <div v-else-if="extError" class="error-message card">
          {{ extError }}
          <button @click="extError = null">关闭</button>
        </div>

        <div v-else-if="extResults.length > 0" class="results-list">
          <article v-for="item in extResults" :key="item.url" class="result-card card ext-card">
            <div class="result-content" @click="openArticle(item.url)">
              <div class="result-header">
                <span class="result-source">{{ item.source_name || item.engine || '外部' }}</span>
                <span class="result-date">{{ formatDate(item.published_at) }}</span>
                <span v-if="item.score" class="result-score">{{ item.score.toFixed(2) }}</span>
              </div>
              <h3 class="result-title">{{ item.title }}</h3>
              <p v-if="item.description" class="result-description">{{ item.description }}</p>
            </div>
            <div class="ingest-action">
              <button
                v-if="!ingestStatus[item.url] || ingestStatus[item.url] === 'idle'"
                class="btn-ingest"
                title="入库到站内"
                @click.stop="handleIngest(item)"
              >+</button>
              <span v-else-if="ingestStatus[item.url] === 'ingesting'" class="ingest-spinner"></span>
              <span v-else-if="ingestStatus[item.url] === 'success'" class="ingest-ok" title="已入库">&#10003;</span>
              <span v-else-if="ingestStatus[item.url] === 'failed'" class="ingest-fail" title="入库失败">&#10007;</span>
            </div>
          </article>
        </div>

        <div v-else-if="!searchQuery" class="empty-state">
          <div class="empty-icon">&#x1F310;</div>
          <h3>外部搜索</h3>
          <p>通过 SearXNG 搜索互联网内容，点击"+"将结果入库到站内。</p>
        </div>
      </template>
    </main>
  </div>
</template>

<style scoped>
.search-page { position: relative; }
.main-content { padding: var(--space-6) var(--space-8); max-width: 900px; margin: 0 auto; }
.search-section { margin-bottom: var(--space-8); }
.search-title { font-family: var(--font-display); font-size: var(--text-3xl); color: var(--color-neutral-800); margin-bottom: var(--space-6); text-align: center; }

/* Tab Bar */
.tab-bar { display: flex; justify-content: center; gap: var(--space-2); margin-top: var(--space-4); margin-bottom: var(--space-4); }
.tab-btn { padding: var(--space-2) var(--space-5); border: 1px solid var(--color-neutral-300); border-radius: var(--radius-full); background: var(--color-neutral-50); color: var(--color-neutral-600); font-size: var(--text-sm); cursor: pointer; transition: all var(--transition-fast); }
.tab-btn:hover { background: var(--color-neutral-100); }
.tab-btn.active { background: var(--color-primary-500); color: white; border-color: var(--color-primary-500); }

.search-options { display: flex; justify-content: center; margin-top: var(--space-4); }
.option-group { display: flex; align-items: center; gap: var(--space-3); }
.option-group label { font-size: var(--text-sm); color: var(--color-neutral-600); }
.option-group select { width: auto; padding: var(--space-2) var(--space-3); font-size: var(--text-sm); }

.results-info { text-align: center; color: var(--color-neutral-600); margin-bottom: var(--space-6); }
.took-time { color: var(--color-neutral-400); font-size: var(--text-sm); }

.loading { display: flex; flex-direction: column; align-items: center; gap: var(--space-4); padding: var(--space-16); color: var(--color-neutral-500); }
.spinner { width: 40px; height: 40px; border: 3px solid var(--color-neutral-200); border-top-color: var(--color-primary-500); border-radius: 50%; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.results-list { display: flex; flex-direction: column; gap: var(--space-4); }
.result-card { display: flex; gap: var(--space-4); padding: var(--space-4); cursor: pointer; transition: all var(--transition-fast); }
.result-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-lg); }

.result-image { flex-shrink: 0; width: 120px; height: 90px; border-radius: var(--radius-md); overflow: hidden; background: var(--color-neutral-100); }
.result-image img { width: 100%; height: 100%; object-fit: cover; }
.result-content { flex: 1; min-width: 0; }
.result-header { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-2); }
.result-source { font-size: var(--text-xs); font-weight: 600; color: var(--color-primary-600); background: var(--color-primary-50); padding: 2px var(--space-2); border-radius: var(--radius-full); }
.result-date { font-size: var(--text-xs); color: var(--color-neutral-400); }
.result-score { font-size: var(--text-xs); color: var(--color-neutral-400); margin-left: auto; }
.result-title { font-size: var(--text-base); font-weight: 600; color: var(--color-neutral-800); line-height: 1.4; margin-bottom: var(--space-2); }
.result-title :deep(mark) { background: var(--color-primary-100); color: var(--color-primary-700); padding: 0 2px; border-radius: 2px; }
.result-description { font-size: var(--text-sm); color: var(--color-neutral-600); line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.result-description :deep(mark) { background: var(--color-primary-100); color: var(--color-primary-700); padding: 0 2px; border-radius: 2px; }
.result-tags { display: flex; gap: var(--space-1); margin-top: var(--space-2); }
.tag { background: var(--color-neutral-100); color: var(--color-neutral-600); padding: 2px var(--space-2); border-radius: var(--radius-full); font-size: 10px; }

.load-more { display: flex; justify-content: center; padding: var(--space-6); }

/* External card ingest button */
.ext-card { position: relative; }
.ingest-action { display: flex; align-items: center; justify-content: center; flex-shrink: 0; width: 40px; }
.btn-ingest { width: 32px; height: 32px; border-radius: 50%; border: 2px solid var(--color-primary-500); background: white; color: var(--color-primary-500); font-size: 20px; font-weight: 700; line-height: 1; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all var(--transition-fast); }
.btn-ingest:hover { background: var(--color-primary-500); color: white; }
.ingest-spinner { width: 24px; height: 24px; border: 3px solid var(--color-neutral-200); border-top-color: var(--color-primary-500); border-radius: 50%; animation: spin 0.8s linear infinite; }
.ingest-ok { color: var(--color-success, #22c55e); font-size: 20px; font-weight: 700; }
.ingest-fail { color: var(--color-error, #ef4444); font-size: 20px; font-weight: 700; cursor: pointer; }

/* Empty State */
.empty-state { text-align: center; padding: var(--space-16); }
.empty-icon { font-size: 64px; margin-bottom: var(--space-4); }
.empty-state h3 { font-size: var(--text-xl); color: var(--color-neutral-800); margin-bottom: var(--space-2); }
.empty-state p { color: var(--color-neutral-500); margin-bottom: var(--space-4); }
.search-tips { text-align: left; max-width: 400px; margin: var(--space-6) auto 0; background: var(--color-neutral-50); padding: var(--space-4); border-radius: var(--radius-lg); }
.search-tips p { margin-bottom: var(--space-2); }
.search-tips ul { list-style: disc; padding-left: var(--space-6); color: var(--color-neutral-600); font-size: var(--text-sm); }
.search-tips li { margin-bottom: var(--space-1); }

.error-message { background: rgba(239, 68, 68, 0.1); border: 1px solid var(--color-error); color: var(--color-error); padding: var(--space-4); display: flex; justify-content: space-between; align-items: center; }
.error-message button { background: none; border: none; color: var(--color-error); cursor: pointer; font-weight: 600; }
</style>