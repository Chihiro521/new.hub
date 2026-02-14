<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useSourceStore } from '@/stores/sources'
import type { SourceResponse, SourceStatus } from '@/api/sources'
import AddSourceModal from '@/components/AddSourceModal.vue'
import CrawlerLogs from '@/components/CrawlerLogs.vue'

const router = useRouter()
const authStore = useAuthStore()
const sourceStore = useSourceStore()

const showAddModal = ref(false)
const showLogs = ref(false)
const filterStatus = ref<SourceStatus | ''>('')

onMounted(() => {
  sourceStore.fetchSources()
})

function handleLogout() {
  authStore.logout()
  router.push('/login')
}

function getStatusColor(status: SourceStatus): string {
  switch (status) {
    case 'active': return 'status-active'
    case 'paused': return 'status-paused'
    case 'error': return 'status-error'
    case 'pending': return 'status-pending'
    default: return ''
  }
}

function getStatusLabel(status: SourceStatus): string {
  switch (status) {
    case 'active': return 'Active'
    case 'paused': return 'Paused'
    case 'error': return 'Error'
    case 'pending': return 'Pending'
    default: return status
  }
}

function getTypeLabel(type: string): string {
  switch (type) {
    case 'rss': return 'RSS'
    case 'api': return 'API'
    case 'html': return 'HTML'
    default: return type.toUpperCase()
  }
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  const date = new Date(dateStr)
  return date.toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

async function handleRefresh(source: SourceResponse) {
  await sourceStore.refreshSource(source.id)
}

async function handleDelete(source: SourceResponse) {
  if (confirm(`Delete "${source.name}"? This will also delete all collected news.`)) {
    await sourceStore.deleteSource(source.id)
  }
}

async function handleFilter() {
  if (filterStatus.value) {
    await sourceStore.fetchSources({ status: filterStatus.value })
  } else {
    await sourceStore.fetchSources()
  }
}

function handleSourceAdded() {
  showAddModal.value = false
}
</script>

<template>
  <div class="sources-page">
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
          <router-link to="/" class="nav-link">Home</router-link>
          <router-link to="/sources" class="nav-link active">Sources</router-link>
          <router-link to="/search" class="nav-link">Search</router-link>
          <router-link to="/settings" class="nav-link">Settings</router-link>
        </nav>
      </div>
      <div class="user-menu">
        <span class="username">{{ authStore.username }}</span>
        <button class="btn-secondary logout-btn" @click="handleLogout">Logout</button>
      </div>
    </header>

    <!-- Main -->
    <main class="main-content">
      <!-- Page header -->
      <div class="page-header">
        <div>
          <h2>News Sources</h2>
          <p class="subtitle">Manage your news feeds and data sources</p>
        </div>
        <div class="header-actions">
          <button class="btn-secondary" @click="showLogs = !showLogs" style="margin-right: 1rem">
            {{ showLogs ? 'Hide Logs' : 'Show Logs' }}
          </button>
          <button class="btn-primary" @click="showAddModal = true">
            + Add Source
          </button>
        </div>
      </div>

      <!-- Crawler Logs -->
      <CrawlerLogs v-if="showLogs" style="margin-bottom: var(--space-6)" />

      <!-- Filters -->
      <div class="filters card">
        <div class="filter-group">
          <label>Status</label>
          <select v-model="filterStatus" @change="handleFilter" class="input">
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="paused">Paused</option>
            <option value="error">Error</option>
            <option value="pending">Pending</option>
          </select>
        </div>
        <div class="filter-stats">
          <span class="stat">
            <strong>{{ sourceStore.sourceCount }}</strong> sources
          </span>
          <span class="stat">
            <strong>{{ sourceStore.activeSources.length }}</strong> active
          </span>
          <span class="stat error" v-if="sourceStore.errorSources.length > 0">
            <strong>{{ sourceStore.errorSources.length }}</strong> errors
          </span>
        </div>
      </div>

      <!-- Loading -->
      <div v-if="sourceStore.loading" class="loading">
        <div class="spinner"></div>
        <span>Loading sources...</span>
      </div>

      <!-- Error -->
      <div v-else-if="sourceStore.error" class="error-message card">
        {{ sourceStore.error }}
        <button @click="sourceStore.clearError">Dismiss</button>
      </div>

      <!-- Empty state -->
      <div v-else-if="sourceStore.sources.length === 0" class="empty-state card">
        <div class="empty-icon">+</div>
        <h3>No sources yet</h3>
        <p>Add your first news source to start collecting articles.</p>
        <button class="btn-primary" @click="showAddModal = true">Add Source</button>
      </div>

      <!-- Source list -->
      <div v-else class="source-list">
        <div
          v-for="source in sourceStore.sources"
          :key="source.id"
          class="source-card card"
        >
          <div class="source-header">
            <div class="source-icon" :class="source.source_type">
              {{ getTypeLabel(source.source_type) }}
            </div>
            <div class="source-info">
              <h3>{{ source.name }}</h3>
              <a :href="source.url" target="_blank" class="source-url">{{ source.url }}</a>
            </div>
            <div class="source-status" :class="getStatusColor(source.status)">
              {{ getStatusLabel(source.status) }}
            </div>
          </div>

          <p v-if="source.description" class="source-description">
            {{ source.description }}
          </p>

          <div class="source-meta">
            <span class="meta-item">
              <strong>{{ source.item_count }}</strong> items
            </span>
            <span class="meta-item">
              <strong>{{ source.fetch_count }}</strong> fetches
            </span>
            <span class="meta-item">
              Last: {{ formatDate(source.last_fetched_at) }}
            </span>
          </div>

          <div v-if="source.tags.length > 0" class="source-tags">
            <span v-for="tag in source.tags" :key="tag" class="tag">{{ tag }}</span>
          </div>

          <div v-if="source.last_error" class="source-error">
            {{ source.last_error }}
          </div>

          <div class="source-actions">
            <button class="btn-sm" @click="handleRefresh(source)">Refresh</button>
            <button class="btn-sm btn-danger" @click="handleDelete(source)">Delete</button>
          </div>
        </div>
      </div>
    </main>

    <!-- Add Source Modal -->
    <AddSourceModal
      v-if="showAddModal"
      @close="showAddModal = false"
      @added="handleSourceAdded"
    />
  </div>
</template>

<style scoped>
.sources-page {
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
  opacity: 0.3;
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
  padding: var(--space-8);
  max-width: 1000px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--space-6);
}

.header-actions {
  display: flex;
  align-items: center;
}

.page-header h2 {
  font-family: var(--font-display);
  font-size: var(--text-3xl);
  color: var(--color-neutral-800);
}

.subtitle {
  color: var(--color-neutral-500);
  margin-top: var(--space-1);
}

/* Filters */
.filters {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-6);
  padding: var(--space-4);
}

.filter-group {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.filter-group label {
  font-weight: 500;
  color: var(--color-neutral-600);
}

.filter-group select {
  width: auto;
  padding: var(--space-2) var(--space-4);
}

.filter-stats {
  display: flex;
  gap: var(--space-6);
}

.stat {
  color: var(--color-neutral-500);
  font-size: var(--text-sm);
}

.stat.error {
  color: var(--color-error);
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
  width: 80px;
  height: 80px;
  margin: 0 auto var(--space-6);
  background: var(--gradient-soft);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-4xl);
  color: var(--color-primary-400);
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

/* Source list */
.source-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.source-card {
  padding: var(--space-5);
}

.source-header {
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
  margin-bottom: var(--space-3);
}

.source-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
  font-weight: 700;
  color: white;
  flex-shrink: 0;
}

.source-icon.rss {
  background: linear-gradient(135deg, #f97316, #ea580c);
}

.source-icon.api {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
}

.source-icon.html {
  background: linear-gradient(135deg, #8b5cf6, #7c3aed);
}

.source-info {
  flex: 1;
  min-width: 0;
}

.source-info h3 {
  font-size: var(--text-lg);
  color: var(--color-neutral-800);
  margin-bottom: var(--space-1);
}

.source-url {
  font-size: var(--text-sm);
  color: var(--color-neutral-500);
  text-decoration: none;
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.source-url:hover {
  color: var(--color-primary-500);
}

.source-status {
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 600;
}

.status-active {
  background: rgba(16, 185, 129, 0.1);
  color: var(--color-success);
}

.status-paused {
  background: rgba(245, 158, 11, 0.1);
  color: var(--color-warning);
}

.status-error {
  background: rgba(239, 68, 68, 0.1);
  color: var(--color-error);
}

.status-pending {
  background: rgba(59, 130, 246, 0.1);
  color: var(--color-info);
}

.source-description {
  font-size: var(--text-sm);
  color: var(--color-neutral-600);
  margin-bottom: var(--space-3);
}

.source-meta {
  display: flex;
  gap: var(--space-6);
  font-size: var(--text-sm);
  color: var(--color-neutral-500);
  margin-bottom: var(--space-3);
}

.source-tags {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin-bottom: var(--space-3);
}

.tag {
  background: var(--color-primary-50);
  color: var(--color-primary-600);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
}

.source-error {
  background: rgba(239, 68, 68, 0.1);
  color: var(--color-error);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  margin-bottom: var(--space-3);
}

.source-actions {
  display: flex;
  gap: var(--space-2);
  padding-top: var(--space-3);
  border-top: 1px solid var(--color-neutral-100);
}

.btn-sm {
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-neutral-200);
  background: white;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-sm:hover {
  border-color: var(--color-primary-300);
  color: var(--color-primary-600);
}

.btn-sm.btn-danger {
  color: var(--color-error);
}

.btn-sm.btn-danger:hover {
  background: rgba(239, 68, 68, 0.1);
  border-color: var(--color-error);
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
