<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTagStore } from '@/stores/tags'
import type { TagRuleResponse, TagRuleCreate, TagRuleUpdate, MatchMode } from '@/api/tags'

const router = useRouter()
const authStore = useAuthStore()
const tagStore = useTagStore()

// State
const showModal = ref(false)
const isEditing = ref(false)
const showTestModal = ref(false)
const testText = ref('')
const testResult = ref<string[]>([])
const isTesting = ref(false)

// Form State
const formData = ref<TagRuleCreate>({
  tag_name: '',
  keywords: [],
  match_mode: 'any',
  case_sensitive: false,
  match_title: true,
  match_description: true,
  match_content: false,
  priority: 0
})
const editingId = ref<string | null>(null)
const keywordInput = ref('')

// Computed
const sortedRules = computed(() => tagStore.rules)

onMounted(() => {
  tagStore.fetchRules()
  tagStore.fetchStats()
})

// Methods
function handleLogout() {
  authStore.logout()
  router.push('/login')
}

function openCreateModal() {
  isEditing.value = false
  editingId.value = null
  formData.value = {
    tag_name: '',
    keywords: [],
    match_mode: 'any',
    case_sensitive: false,
    match_title: true,
    match_description: true,
    match_content: false,
    priority: 0
  }
  showModal.value = true
}

function openEditModal(rule: TagRuleResponse) {
  isEditing.value = true
  editingId.value = rule.id
  formData.value = {
    tag_name: rule.tag_name,
    keywords: [...rule.keywords],
    match_mode: rule.match_mode,
    case_sensitive: rule.case_sensitive,
    match_title: rule.match_title,
    match_description: rule.match_description,
    match_content: rule.match_content,
    priority: rule.priority
  }
  showModal.value = true
}

async function handleSubmit() {
  if (!formData.value.tag_name || formData.value.keywords.length === 0) return

  if (isEditing.value && editingId.value) {
    await tagStore.updateRule(editingId.value, formData.value)
  } else {
    await tagStore.createRule(formData.value)
  }
  showModal.value = false
  tagStore.fetchStats()
}

async function handleDelete(rule: TagRuleResponse) {
  if (confirm(`Delete rule "${rule.tag_name}"?`)) {
    await tagStore.deleteRule(rule.id)
    tagStore.fetchStats()
  }
}

async function handleToggleActive(rule: TagRuleResponse) {
  await tagStore.toggleRuleActive(rule.id)
}

function addKeyword() {
  const kw = keywordInput.value.trim()
  if (kw && !formData.value.keywords.includes(kw)) {
    formData.value.keywords.push(kw)
  }
  keywordInput.value = ''
}

function removeKeyword(index: number) {
  formData.value.keywords.splice(index, 1)
}

async function runTest() {
  if (!testText.value) return
  isTesting.value = true
  testResult.value = await tagStore.extractKeywords(testText.value)
  isTesting.value = false
}

function useExtractedKeyword(kw: string) {
  if (!formData.value.keywords.includes(kw)) {
    formData.value.keywords.push(kw)
  }
}
</script>

<template>
  <div class="tags-page">
    <div class="bg-decoration">
      <div class="circle circle-1"></div>
      <div class="circle circle-2"></div>
    </div>

    <header class="header glass">
      <div class="header-left">
        <h1 class="logo gradient-text">News Hub</h1>
        <nav class="nav">
          <router-link to="/" class="nav-link">Home</router-link>
          <router-link to="/sources" class="nav-link">Sources</router-link>
          <router-link to="/tags" class="nav-link active">Tags</router-link>
          <router-link to="/search" class="nav-link">Search</router-link>
          <router-link to="/settings" class="nav-link">Settings</router-link>
          <router-link to="/assistant" class="nav-link">AI</router-link>
        </nav>
      </div>
      <div class="user-menu">
        <span class="username">{{ authStore.username }}</span>
        <button class="btn-secondary logout-btn" @click="handleLogout">Logout</button>
      </div>
    </header>

    <main class="main-content">
      <div class="page-header">
        <div>
          <h2>Tag Rules</h2>
          <p class="subtitle">Manage auto-tagging rules for your news feed</p>
        </div>
        <div class="header-actions">
          <button class="btn-secondary" @click="showTestModal = true">Test Extraction</button>
          <button class="btn-primary" @click="openCreateModal">+ Create Rule</button>
        </div>
      </div>

      <!-- Stats -->
      <div class="stats-grid" v-if="tagStore.stats">
        <div class="stat-card glass">
          <div class="stat-value">{{ tagStore.stats.rules_count }}</div>
          <div class="stat-label">Active Rules</div>
        </div>
        <div class="stat-card glass">
          <div class="stat-value">{{ tagStore.stats.unique_tags }}</div>
          <div class="stat-label">Unique Tags</div>
        </div>
        <div class="stat-card glass">
          <div class="stat-value">{{ tagStore.stats.total_tagged_items }}</div>
          <div class="stat-label">Tagged Articles</div>
        </div>
      </div>

      <!-- Rules List -->
      <div class="rules-list">
        <div v-if="tagStore.loading && tagStore.rules.length === 0" class="loading">
          Loading rules...
        </div>
        
        <div v-else-if="tagStore.rules.length === 0" class="empty-state glass">
          <h3>No Tag Rules</h3>
          <p>Create rules to automatically categorize your news.</p>
          <button class="btn-primary" @click="openCreateModal">Create First Rule</button>
        </div>

        <div v-else v-for="rule in sortedRules" :key="rule.id" class="rule-card glass" :class="{ inactive: !rule.is_active }">
          <div class="rule-header">
            <div class="rule-title">
              <span class="tag-badge">{{ rule.tag_name }}</span>
              <span class="priority-badge">P{{ rule.priority }}</span>
            </div>
            <div class="rule-actions">
              <label class="switch">
                <input type="checkbox" :checked="rule.is_active" @change="handleToggleActive(rule)">
                <span class="slider round"></span>
              </label>
              <button class="btn-icon" @click="openEditModal(rule)">✎</button>
              <button class="btn-icon delete" @click="handleDelete(rule)">×</button>
            </div>
          </div>

          <div class="rule-keywords">
            <span class="keyword-label">Keywords ({{ rule.match_mode }}):</span>
            <div class="keyword-chips">
              <span v-for="kw in rule.keywords" :key="kw" class="chip">{{ kw }}</span>
            </div>
          </div>

          <div class="rule-meta">
            <span>Matches: {{ rule.match_count }}</span>
            <span v-if="rule.match_title">Title</span>
            <span v-if="rule.match_description">Desc</span>
            <span v-if="rule.match_content">Content</span>
          </div>
        </div>
      </div>
    </main>

    <!-- Create/Edit Modal -->
    <div v-if="showModal" class="modal-backdrop" @click.self="showModal = false">
      <div class="modal glass-strong">
        <h3>{{ isEditing ? 'Edit Rule' : 'Create Tag Rule' }}</h3>
        
        <div class="form-group">
          <label>Tag Name</label>
          <input v-model="formData.tag_name" class="input" placeholder="e.g., Technology" autofocus>
        </div>

        <div class="form-group">
          <label>Keywords (Press Enter)</label>
          <div class="keywords-input-container input">
            <span v-for="(kw, idx) in formData.keywords" :key="idx" class="chip removable">
              {{ kw }}
              <span @click="removeKeyword(idx)">×</span>
            </span>
            <input 
              v-model="keywordInput" 
              @keydown.enter.prevent="addKeyword"
              @keydown.backspace="keywordInput === '' && formData.keywords.length && removeKeyword(formData.keywords.length - 1)"
              placeholder="Add keyword..."
              class="transparent-input"
            >
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Match Mode</label>
            <select v-model="formData.match_mode" class="input">
              <option value="any">Any Keyword</option>
              <option value="all">All Keywords</option>
            </select>
          </div>
          <div class="form-group">
            <label>Priority</label>
            <input type="number" v-model="formData.priority" class="input" min="0" max="100">
          </div>
        </div>

        <div class="form-group checkbox-group">
          <label><input type="checkbox" v-model="formData.match_title"> Title</label>
          <label><input type="checkbox" v-model="formData.match_description"> Description</label>
          <label><input type="checkbox" v-model="formData.match_content"> Content</label>
          <label><input type="checkbox" v-model="formData.case_sensitive"> Case Sensitive</label>
        </div>

        <div class="modal-actions">
          <button class="btn-secondary" @click="showModal = false">Cancel</button>
          <button class="btn-primary" @click="handleSubmit">Save Rule</button>
        </div>
      </div>
    </div>

    <!-- Test Modal -->
    <div v-if="showTestModal" class="modal-backdrop" @click.self="showTestModal = false">
      <div class="modal glass-strong">
        <h3>Test Keyword Extraction</h3>
        <p class="modal-subtitle">Paste text to see what keywords Jieba extracts.</p>
        
        <textarea v-model="testText" class="input textarea" placeholder="Paste article text here..." rows="6"></textarea>
        
        <div class="test-results" v-if="testResult.length > 0">
          <h4>Extracted Keywords:</h4>
          <div class="keyword-chips">
            <span v-for="kw in testResult" :key="kw" class="chip clickable" @click="useExtractedKeyword(kw)">
              {{ kw }}
            </span>
          </div>
          <p class="hint">Click a keyword to add it to your current rule (if open).</p>
        </div>

        <div class="modal-actions">
          <button class="btn-secondary" @click="showTestModal = false">Close</button>
          <button class="btn-primary" @click="runTest" :disabled="isTesting">
            {{ isTesting ? 'Extracting...' : 'Extract Keywords' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tags-page {
  min-height: 100vh;
  padding-bottom: 2rem;
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
  top: -100px;
  left: -100px;
}

.circle-2 {
  width: 400px;
  height: 400px;
  background: var(--color-secondary-200);
  bottom: -50px;
  right: -50px;
}

/* Header */
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 2rem;
}

.logo {
  font-family: var(--font-display);
  font-size: 1.5rem;
  font-weight: 700;
}

.nav {
  display: flex;
  gap: 1rem;
}

.nav-link {
  color: var(--color-neutral-600);
  text-decoration: none;
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  transition: all 0.2s;
}

.nav-link:hover, .nav-link.active {
  background: rgba(255, 255, 255, 0.5);
  color: var(--color-primary-600);
}

/* Main */
.main-content {
  max-width: 900px;
  margin: 2rem auto;
  padding: 0 1rem;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 2rem;
}

.header-actions {
  display: flex;
  gap: 1rem;
}

.subtitle {
  color: var(--color-neutral-500);
}

/* Stats */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.stat-card {
  padding: 1.5rem;
  text-align: center;
  border-radius: 1rem;
}

.stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--color-primary-600);
}

.stat-label {
  color: var(--color-neutral-500);
  font-size: 0.9rem;
}

/* Rules List */
.rules-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.rule-card {
  padding: 1.5rem;
  border-radius: 1rem;
  transition: all 0.2s;
}

.rule-card.inactive {
  opacity: 0.7;
  background: rgba(255, 255, 255, 0.1);
}

.rule-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.rule-title {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.tag-badge {
  background: var(--gradient-primary);
  color: white;
  padding: 0.25rem 0.75rem;
  border-radius: 2rem;
  font-weight: 600;
}

.priority-badge {
  font-size: 0.8rem;
  color: var(--color-neutral-500);
  background: rgba(0,0,0,0.05);
  padding: 0.1rem 0.4rem;
  border-radius: 0.25rem;
}

.rule-actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.btn-icon {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 1.2rem;
  color: var(--color-neutral-500);
  padding: 0.25rem;
  border-radius: 0.25rem;
  transition: background 0.2s;
}

.btn-icon:hover {
  background: rgba(0,0,0,0.05);
  color: var(--color-primary-600);
}

.btn-icon.delete:hover {
  color: var(--color-error);
}

.rule-keywords {
  margin-bottom: 0.75rem;
}

.keyword-label {
  font-size: 0.85rem;
  color: var(--color-neutral-500);
  margin-right: 0.5rem;
}

.keyword-chips {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.chip {
  background: white;
  padding: 0.15rem 0.6rem;
  border-radius: 1rem;
  font-size: 0.85rem;
  border: 1px solid var(--color-neutral-200);
}

.rule-meta {
  display: flex;
  gap: 1rem;
  font-size: 0.8rem;
  color: var(--color-neutral-400);
}

/* Modal */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.3);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

.modal {
  width: 90%;
  max-width: 500px;
  padding: 2rem;
  border-radius: 1.5rem;
  box-shadow: 0 10px 25px rgba(0,0,0,0.1);
}

.modal h3 {
  margin-bottom: 1.5rem;
  font-size: 1.5rem;
}

.form-group {
  margin-bottom: 1.2rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
  font-size: 0.9rem;
  color: var(--color-neutral-600);
}

.form-row {
  display: flex;
  gap: 1rem;
}

.keywords-input-container {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  min-height: 42px;
}

.transparent-input {
  border: none;
  background: transparent;
  outline: none;
  flex: 1;
  min-width: 100px;
}

.chip.removable {
  padding-right: 0.4rem;
  display: flex;
  align-items: center;
  gap: 0.3rem;
  background: var(--color-primary-50);
  border-color: var(--color-primary-200);
  color: var(--color-primary-700);
}

.chip.removable span {
  cursor: pointer;
  font-weight: bold;
}

.checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}

.checkbox-group label {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-weight: normal;
  cursor: pointer;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
  margin-top: 2rem;
}

.textarea {
  resize: vertical;
  min-height: 100px;
}

.test-results {
  margin-top: 1.5rem;
  padding-top: 1.5rem;
  border-top: 1px solid rgba(0,0,0,0.1);
}

.hint {
  font-size: 0.8rem;
  color: var(--color-neutral-500);
  margin-top: 0.5rem;
}

.chip.clickable {
  cursor: pointer;
  transition: all 0.2s;
}

.chip.clickable:hover {
  background: var(--color-primary-100);
  border-color: var(--color-primary-300);
}

/* Switch Toggle */
.switch {
  position: relative;
  display: inline-block;
  width: 40px;
  height: 22px;
}

.switch input { 
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  transition: .4s;
  border-radius: 34px;
}

.slider:before {
  position: absolute;
  content: "";
  height: 16px;
  width: 16px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: .4s;
  border-radius: 50%;
}

input:checked + .slider {
  background-color: var(--color-success);
}

input:checked + .slider:before {
  transform: translateX(18px);
}
</style>
