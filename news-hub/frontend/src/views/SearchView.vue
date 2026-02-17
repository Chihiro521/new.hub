<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { searchApi, type SearchResultItem, type SearchType } from '@/api/search'
import SearchBar from '@/components/SearchBar.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const searchQuery = ref('')
const searchType = ref<SearchType>('hybrid')
const results = ref<SearchResultItem[]>([])
const totalResults = ref(0)
const currentPage = ref(1)
const isLoading = ref(false)
const searchTook = ref(0)
const error = ref<string | null>(null)

const pageSize = 20
const hasMore = computed(() => results.value.length < totalResults.value)

onMounted(() => {
  // Get query from URL
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

function handleLogout() {
  authStore.logout()
  router.push('/login')
}

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

function handleSearch(query: string) {
  searchQuery.value = query
  currentPage.value = 1
  results.value = []
  performSearch()
}

function handleSearchTypeChange() {
  currentPage.value = 1
  results.value = []
  performSearch()
}

async function loadMore() {
  if (isLoading.value || !hasMore.value) return
  currentPage.value++
  await performSearch()
}

function openArticle(url: string) {
  window.open(url, '_blank')
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
  })
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
    <!-- Background -->
    <div class="bg-decoration">
      <div class="circle circle-1"></div>
      <div class="circle circle-2"></div>
    </div>

    <!-- Header -->
    <header class="header glass">
      <div class="header-left">
        <h1 class="logo gradient-text">News Hub</h1>
        <nav class="nav">
          <router-link to="/" class="nav-link">新闻</router-link>
          <router-link to="/sources" class="nav-link">订阅源</router-link>
          <router-link to="/settings" class="nav-link">设置</router-link>
          <router-link to="/assistant" class="nav-link">AI 助手</router-link>
        </nav>
      </div>
      <div class="user-menu">
        <span class="username">{{ authStore.username }}</span>
        <button class="btn-secondary logout-btn" @click="handleLogout">退出</button>
      </div>
    </header>

    <!-- Main -->
    <main class="main-content">
      <!-- Search Box -->
      <div class="search-section">
        <h2 class="search-title">搜索新闻</h2>
        <SearchBar
          v-model="searchQuery"
          placeholder="搜索文章..."
          @search="handleSearch"
        />
        
        <!-- Search Type Toggle -->
        <div class="search-options">
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

      <!-- Results Info -->
      <div v-if="totalResults > 0 || searchQuery" class="results-info">
        <span v-if="totalResults > 0">
          找到 <strong>{{ totalResults }}</strong> 条结果
          <span class="took-time">({{ searchTook }}ms)</span>
        </span>
        <span v-else-if="!isLoading && searchQuery">
          未找到"{{ searchQuery }}"的相关结果
        </span>
      </div>

      <!-- Loading -->
      <div v-if="isLoading && results.length === 0" class="loading">
        <div class="spinner"></div>
        <span>搜索中...</span>
      </div>

      <!-- Error -->
      <div v-else-if="error" class="error-message card">
        {{ error }}
        <button @click="error = null">关闭</button>
      </div>

      <!-- Results -->
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
            <h3 
              class="result-title"
              v-html="highlightText(item.title, item.highlights, 'title')"
            ></h3>
            <p 
              v-if="item.description" 
              class="result-description"
              v-html="highlightText(item.description, item.highlights, 'description')"
            ></p>
            <div class="result-tags" v-if="item.tags.length > 0">
              <span v-for="tag in item.tags.slice(0, 3)" :key="tag" class="tag">{{ tag }}</span>
            </div>
          </div>
        </article>

        <!-- Load More -->
        <div v-if="hasMore" class="load-more">
          <button
            class="btn-secondary"
            :disabled="isLoading"
            @click="loadMore"
          >
            {{ isLoading ? '加载中...' : '加载更多' }}
          </button>
        </div>
      </div>

      <!-- Empty state (no query) -->
      <div v-else-if="!searchQuery" class="empty-state">
        <div class="empty-icon">🔍</div>
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
    </main>
  </div>
</template>

<style scoped>
.search-page {
  min-height: 100vh;
  position: relative;
}

/* Background */
.bg-decoration {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: -1;
}

.circle {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.25;
}

.circle-1 {
  width: 500px;
  height: 500px;
  background: var(--color-secondary-200);
  top: -150px;
  left: -100px;
}

.circle-2 {
  width: 400px;
  height: 400px;
  background: var(--color-primary-200);
  bottom: -100px;
  right: -100px;
}

/* Header */
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-4) var(--space-8);
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--space-8);
}

.logo {
  font-family: var(--font-display);
  font-size: var(--text-2xl);
  font-weight: 700;
}

.nav {
  display: flex;
  gap: var(--space-4);
}

.nav-link {
  color: var(--color-neutral-600);
  text-decoration: none;
  font-weight: 500;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
}

.nav-link:hover {
  color: var(--color-primary-600);
  background: var(--color-primary-50);
}

.user-menu {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.username {
  color: var(--color-neutral-600);
  font-weight: 500;
}

.logout-btn {
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-sm);
}

/* Main */
.main-content {
  padding: var(--space-6) var(--space-8);
  max-width: 900px;
  margin: 0 auto;
}

/* Search Section */
.search-section {
  margin-bottom: var(--space-8);
}

.search-title {
  font-family: var(--font-display);
  font-size: var(--text-3xl);
  color: var(--color-neutral-800);
  margin-bottom: var(--space-6);
  text-align: center;
}

.search-options {
  display: flex;
  justify-content: center;
  margin-top: var(--space-4);
}

.option-group {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.option-group label {
  font-size: var(--text-sm);
  color: var(--color-neutral-600);
}

.option-group select {
  width: auto;
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
}

/* Results Info */
.results-info {
  text-align: center;
  color: var(--color-neutral-600);
  margin-bottom: var(--space-6);
}

.took-time {
  color: var(--color-neutral-400);
  font-size: var(--text-sm);
}

/* Loading */
.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-16);
  color: var(--color-neutral-500);
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--color-neutral-200);
  border-top-color: var(--color-primary-500);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Results List */
.results-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.result-card {
  display: flex;
  gap: var(--space-4);
  padding: var(--space-4);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.result-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}

.result-image {
  flex-shrink: 0;
  width: 120px;
  height: 90px;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--color-neutral-100);
}

.result-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.result-content {
  flex: 1;
  min-width: 0;
}

.result-header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.result-source {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-primary-600);
  background: var(--color-primary-50);
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
}

.result-date {
  font-size: var(--text-xs);
  color: var(--color-neutral-400);
}

.result-score {
  font-size: var(--text-xs);
  color: var(--color-neutral-400);
  margin-left: auto;
}

.result-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-neutral-800);
  line-height: 1.4;
  margin-bottom: var(--space-2);
}

.result-title :deep(mark) {
  background: var(--color-primary-100);
  color: var(--color-primary-700);
  padding: 0 2px;
  border-radius: 2px;
}

.result-description {
  font-size: var(--text-sm);
  color: var(--color-neutral-600);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.result-description :deep(mark) {
  background: var(--color-primary-100);
  color: var(--color-primary-700);
  padding: 0 2px;
  border-radius: 2px;
}

.result-tags {
  display: flex;
  gap: var(--space-1);
  margin-top: var(--space-2);
}

.tag {
  background: var(--color-neutral-100);
  color: var(--color-neutral-600);
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  font-size: 10px;
}

/* Load More */
.load-more {
  display: flex;
  justify-content: center;
  padding: var(--space-6);
}

/* Empty State */
.empty-state {
  text-align: center;
  padding: var(--space-16);
}

.empty-icon {
  font-size: 64px;
  margin-bottom: var(--space-4);
}

.empty-state h3 {
  font-size: var(--text-xl);
  color: var(--color-neutral-800);
  margin-bottom: var(--space-2);
}

.empty-state p {
  color: var(--color-neutral-500);
  margin-bottom: var(--space-4);
}

.search-tips {
  text-align: left;
  max-width: 400px;
  margin: var(--space-6) auto 0;
  background: var(--color-neutral-50);
  padding: var(--space-4);
  border-radius: var(--radius-lg);
}

.search-tips p {
  margin-bottom: var(--space-2);
}

.search-tips ul {
  list-style: disc;
  padding-left: var(--space-6);
  color: var(--color-neutral-600);
  font-size: var(--text-sm);
}

.search-tips li {
  margin-bottom: var(--space-1);
}

/* Error */
.error-message {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid var(--color-error);
  color: var(--color-error);
  padding: var(--space-4);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.error-message button {
  background: none;
  border: none;
  color: var(--color-error);
  cursor: pointer;
  font-weight: 600;
}
</style>
