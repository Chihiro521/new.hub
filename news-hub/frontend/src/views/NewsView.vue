<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useNewsStore } from '@/stores/news'
import { useSourceStore } from '@/stores/sources'
import { useTagStore } from '@/stores/tags'
import SearchBar from '@/components/SearchBar.vue'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'

const router = useRouter()
const authStore = useAuthStore()
const newsStore = useNewsStore()
const sourceStore = useSourceStore()
const tagStore = useTagStore()

const filterSource = ref<string>('')
const filterStarred = ref<boolean | null>(null)
const filterUnread = ref<boolean | null>(null)
const filterTag = ref<string>('')

const isLoadingMore = ref(false)

onMounted(async () => {
  await Promise.all([
    newsStore.fetchNews(),
    newsStore.fetchStats(),
    sourceStore.fetchSources(),
    tagStore.fetchUserTags(),
  ])
})

function handleLogout() {
  authStore.logout()
  router.push('/login')
}

async function applyFilters() {
  await newsStore.fetchNews({
    source_id: filterSource.value || undefined,
    tag: filterTag.value || undefined,
    is_starred: filterStarred.value ?? undefined,
    is_read: filterUnread.value === null ? undefined : !filterUnread.value,
  })
}

async function handleTagClick(tag: string) {
  if (filterTag.value === tag) {
    filterTag.value = ''
  } else {
    filterTag.value = tag
  }
  await applyFilters()
}

async function loadMore() {
  if (isLoadingMore.value || !newsStore.hasMore) return
  isLoadingMore.value = true
  await newsStore.loadMore()
  isLoadingMore.value = false
}

async function handleMarkAsRead(newsId: string) {
  await newsStore.markAsRead(newsId)
}

async function handleToggleStar(newsId: string, event: Event) {
  event.stopPropagation()
  await newsStore.toggleStar(newsId)
}

async function handleMarkAllRead() {
  if (confirm('确认将所有新闻标记为已读？')) {
    await newsStore.markAllAsRead(filterSource.value || undefined)
  }
}

function openArticle(url: string, newsId: string) {
  handleMarkAsRead(newsId)
  window.open(url, '_blank')
}

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const hours = Math.floor(diff / 3600000)
  
  if (hours < 1) return '刚刚'
  if (hours < 24) return `${hours}小时前`
  if (hours < 48) return '昨天'
  
  return date.toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
  })
}

const sourceOptions = computed(() => {
  return sourceStore.sources.map(s => ({ id: s.id, name: s.name }))
})
</script>

<template>
  <div class="news-page">
    <!-- Background -->
    <div class="bg-decoration">
      <div class="circle circle-1"></div>
      <div class="circle circle-2"></div>
      <div class="circle circle-3"></div>
    </div>

    <!-- Header -->
    <header class="header glass">
      <div class="header-left">
        <h1 class="logo gradient-text">News Hub</h1>
        <nav class="nav">
          <router-link to="/" class="nav-link active">新闻</router-link>
          <router-link to="/sources" class="nav-link">订阅源</router-link>
          <router-link to="/search" class="nav-link">搜索</router-link>
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
      <!-- Main Layout with Sidebar -->
      <div class="content-layout">
        <!-- Sidebar -->
        <aside class="sidebar glass">
          <div class="sidebar-section">
            <h3>热门标签</h3>
            <div class="tags-cloud">
              <button
                v-for="tag in tagStore.topTags"
                :key="tag.tag_name"
                class="tag-chip"
                :class="{ active: filterTag === tag.tag_name }"
                @click="handleTagClick(tag.tag_name)"
              >
                #{{ tag.tag_name }}
                <span class="tag-count">{{ tag.count }}</span>
              </button>
            </div>
          </div>
        </aside>

        <!-- News Feed -->
        <div class="feed-column">
          <!-- Search Bar -->
          <div class="search-section">
            <SearchBar placeholder="搜索新闻..." />
          </div>

          <!-- Stats Bar -->
          <div class="stats-bar glass">
        <div class="stat-item">
          <span class="stat-value">{{ newsStore.stats.total }}</span>
          <span class="stat-label">总计</span>
        </div>
        <div class="stat-item unread">
          <span class="stat-value">{{ newsStore.stats.unread }}</span>
          <span class="stat-label">未读</span>
        </div>
        <div class="stat-item starred">
          <span class="stat-value">{{ newsStore.stats.starred }}</span>
          <span class="stat-label">收藏</span>
        </div>
        <button class="btn-sm" @click="handleMarkAllRead">全部已读</button>
      </div>

      <!-- Filters -->
      <div class="filters card">
        <div class="filter-group">
          <label>订阅源</label>
          <select v-model="filterSource" @change="applyFilters" class="input">
            <option value="">全部来源</option>
            <option v-for="source in sourceOptions" :key="source.id" :value="source.id">
              {{ source.name }}
            </option>
          </select>
        </div>
        <div class="filter-group">
          <label>状态</label>
          <select v-model="filterUnread" @change="applyFilters" class="input">
            <option :value="null">全部</option>
            <option :value="true">仅未读</option>
            <option :value="false">仅已读</option>
          </select>
        </div>
        <div class="filter-group">
          <label>收藏</label>
          <select v-model="filterStarred" @change="applyFilters" class="input">
            <option :value="null">全部</option>
            <option :value="true">仅收藏</option>
          </select>
        </div>
      </div>

      <!-- Loading -->
      <div v-if="newsStore.loading && newsStore.newsList.length === 0" class="loading">
        <LoadingSkeleton type="card" :count="5" />
      </div>

      <!-- Error -->
      <div v-else-if="newsStore.error" class="error-message card">
        {{ newsStore.error }}
        <button @click="newsStore.clearError">关闭</button>
      </div>

      <!-- Empty state -->
      <div v-else-if="newsStore.newsList.length === 0" class="empty-state card">
        <div class="empty-icon">📰</div>
        <h3>暂无新闻</h3>
        <p>添加一些订阅源并刷新，即可开始收集新闻。</p>
        <router-link to="/sources" class="btn-primary">管理订阅源</router-link>
      </div>

          <!-- News list -->
          <div v-else class="news-list">
            <article
              v-for="item in newsStore.newsList"
              :key="item.id"
              class="news-card card"
              :class="{ 'is-read': item.is_read }"
              @click="openArticle(item.url, item.id)"
            >
              <div class="news-image" v-if="item.image_url">
                <img :src="item.image_url" :alt="item.title" loading="lazy" />
              </div>
              <div class="news-content">
                <div class="news-header">
                  <span class="news-source">{{ item.source_name }}</span>
                  <span class="news-date">{{ formatDate(item.published_at || item.crawled_at) }}</span>
                </div>
                <h3 class="news-title">{{ item.title }}</h3>
                <p v-if="item.description" class="news-description">
                  {{ item.description }}
                </p>
                <div class="news-footer">
                  <div class="news-tags" v-if="item.tags.length > 0">
                    <span 
                      v-for="tag in item.tags.slice(0, 3)" 
                      :key="tag" 
                      class="tag"
                      @click.stop="handleTagClick(tag)"
                    >
                      {{ tag }}
                    </span>
                  </div>
                  <button
                    class="star-btn"
                    :class="{ 'is-starred': item.is_starred }"
                    @click="handleToggleStar(item.id, $event)"
                  >
                    {{ item.is_starred ? '★' : '☆' }}
                  </button>
                </div>
              </div>
            </article>

            <!-- Load more -->
            <div v-if="newsStore.hasMore" class="load-more">
              <button
                class="btn-secondary"
                :disabled="isLoadingMore"
                @click="loadMore"
              >
                {{ isLoadingMore ? '加载中...' : '加载更多' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.news-page {
  min-height: 100vh;
  position: relative;
}

/* Layout */
.content-layout {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: var(--space-6);
  align-items: start;
}

/* Sidebar */
.sidebar {
  position: sticky;
  top: 100px;
  padding: var(--space-4);
  border-radius: var(--radius-lg);
  max-height: calc(100vh - 120px);
  overflow-y: auto;
}

.sidebar h3 {
  font-size: var(--text-sm);
  text-transform: uppercase;
  color: var(--color-neutral-500);
  margin-bottom: var(--space-3);
  letter-spacing: 0.05em;
}

.tags-cloud {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.tag-chip {
  background: none;
  border: 1px solid transparent;
  color: var(--color-neutral-600);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  cursor: pointer;
  text-align: left;
  display: flex;
  justify-content: space-between;
  transition: all var(--transition-fast);
}

.tag-chip:hover {
  background: var(--color-primary-50);
  color: var(--color-primary-600);
}

.tag-chip.active {
  background: var(--color-primary-100);
  color: var(--color-primary-700);
  border-color: var(--color-primary-200);
  font-weight: 600;
}

.tag-count {
  font-size: var(--text-xs);
  color: var(--color-neutral-400);
  background: var(--color-neutral-100);
  padding: 0 6px;
  border-radius: var(--radius-full);
}

/* Feed Column */
.feed-column {
  min-width: 0;
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
  background: var(--color-primary-200);
  top: -150px;
  right: -100px;
}

.circle-2 {
  width: 400px;
  height: 400px;
  background: var(--color-secondary-200);
  bottom: -100px;
  left: -100px;
}

.circle-3 {
  width: 300px;
  height: 300px;
  background: var(--color-primary-300);
  top: 40%;
  left: 50%;
  transform: translateX(-50%);
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

.nav-link.active {
  color: var(--color-primary-600);
  background: var(--color-primary-100);
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
  display: flex;
  justify-content: center;
  margin-bottom: var(--space-6);
}

/* Stats Bar */
.stats-bar {
  display: flex;
  align-items: center;
  gap: var(--space-8);
  padding: var(--space-4) var(--space-6);
  margin-bottom: var(--space-6);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-value {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--color-neutral-800);
}

.stat-item.unread .stat-value {
  color: var(--color-primary-600);
}

.stat-item.starred .stat-value {
  color: var(--color-warning);
}

.stat-label {
  font-size: var(--text-xs);
  color: var(--color-neutral-500);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stats-bar .btn-sm {
  margin-left: auto;
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-sm);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-neutral-200);
  background: white;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.stats-bar .btn-sm:hover {
  border-color: var(--color-primary-300);
  color: var(--color-primary-600);
}

/* Filters */
.filters {
  display: flex;
  gap: var(--space-6);
  align-items: flex-end;
  margin-bottom: var(--space-6);
  padding: var(--space-4);
}

.filter-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.filter-group label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-neutral-500);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.filter-group select {
  width: 160px;
  padding: var(--space-2) var(--space-3);
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

/* Empty state */
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
  margin-bottom: var(--space-6);
}

/* News list */
.news-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.news-card {
  display: flex;
  gap: var(--space-4);
  padding: var(--space-4);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.news-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}

.news-card.is-read {
  opacity: 0.7;
}

.news-card.is-read .news-title {
  color: var(--color-neutral-500);
}

.news-image {
  flex-shrink: 0;
  width: 140px;
  height: 100px;
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--color-neutral-100);
}

.news-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.news-content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.news-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-2);
}

.news-source {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-primary-600);
  background: var(--color-primary-50);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-full);
}

.news-date {
  font-size: var(--text-xs);
  color: var(--color-neutral-400);
}

.news-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-neutral-800);
  line-height: 1.4;
  margin-bottom: var(--space-2);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.news-description {
  font-size: var(--text-sm);
  color: var(--color-neutral-600);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: var(--space-2);
}

.news-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: auto;
}

.news-tags {
  display: flex;
  gap: var(--space-1);
}

.tag {
  background: var(--color-neutral-100);
  color: var(--color-neutral-600);
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  font-size: 10px;
}

.star-btn {
  background: none;
  border: none;
  font-size: var(--text-xl);
  cursor: pointer;
  color: var(--color-neutral-300);
  transition: all var(--transition-fast);
  padding: var(--space-1);
}

.star-btn:hover {
  color: var(--color-warning);
  transform: scale(1.2);
}

.star-btn.is-starred {
  color: var(--color-warning);
}

/* Load more */
.load-more {
  display: flex;
  justify-content: center;
  padding: var(--space-6);
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

/* Responsive */
@media (max-width: 900px) {
  .content-layout {
    grid-template-columns: 1fr;
  }

  .sidebar {
    display: none; /* Hide sidebar on small screens for now */
  }
}

@media (max-width: 640px) {
  .news-image {
    width: 100px;
    height: 80px;
  }

  .filters {
    flex-wrap: wrap;
  }

  .filter-group select {
    width: 140px;
  }

  .stats-bar {
    flex-wrap: wrap;
    gap: var(--space-4);
  }
}
</style>
