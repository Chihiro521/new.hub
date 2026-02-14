<script setup lang="ts">
import { ref, computed } from 'vue'
import { sourceApi, type SourceType, type SourceDetectResponse, type SourceCreate } from '@/api'
import { useSourceStore } from '@/stores/sources'

const emit = defineEmits<{
  close: []
  added: []
}>()

const sourceStore = useSourceStore()

// Form state
const step = ref<'url' | 'config'>('url')
const url = ref('')
const detecting = ref(false)
const detectError = ref('')
const detectResult = ref<SourceDetectResponse | null>(null)

// Config form
const name = ref('')
const sourceType = ref<SourceType>('rss')
const description = ref('')
const tags = ref('')
const refreshInterval = ref(30)

const isValidUrl = computed(() => {
  try {
    new URL(url.value)
    return true
  } catch {
    return false
  }
})

async function handleDetect() {
  if (!isValidUrl.value) return

  detecting.value = true
  detectError.value = ''

  try {
    const response = await sourceApi.detect(url.value)
    detectResult.value = response.data

    // Pre-fill form with detected values
    if (response.data.suggested_name) {
      name.value = response.data.suggested_name
    }
    sourceType.value = response.data.detected_type

    step.value = 'config'
  } catch (e) {
    detectError.value = e instanceof Error ? e.message : 'Detection failed'
  } finally {
    detecting.value = false
  }
}

async function handleCreate() {
  const data: SourceCreate = {
    name: name.value,
    url: url.value,
    source_type: sourceType.value,
    description: description.value || undefined,
    tags: tags.value ? tags.value.split(',').map(t => t.trim()).filter(Boolean) : undefined,
    refresh_interval_minutes: refreshInterval.value,
    parser_config: detectResult.value?.suggested_config || undefined
  }

  const result = await sourceStore.createSource(data)
  if (result) {
    emit('added')
  }
}

function handleBack() {
  step.value = 'url'
  detectResult.value = null
}

function getTypeLabel(type: SourceType): string {
  switch (type) {
    case 'rss': return 'RSS Feed'
    case 'api': return 'JSON API'
    case 'html': return 'HTML Scraping'
  }
}

function getConfidenceLabel(confidence: number): string {
  if (confidence >= 0.8) return 'High'
  if (confidence >= 0.5) return 'Medium'
  return 'Low'
}
</script>

<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal glass-strong">
      <div class="modal-header">
        <h2>Add News Source</h2>
        <button class="close-btn" @click="$emit('close')">x</button>
      </div>

      <!-- Step 1: URL Input -->
      <div v-if="step === 'url'" class="modal-body">
        <p class="step-description">
          Enter the URL of a news source. We'll automatically detect its type and configuration.
        </p>

        <div class="form-group">
          <label for="url">Source URL</label>
          <input
            id="url"
            v-model="url"
            type="url"
            class="input"
            placeholder="https://example.com/feed.xml"
            @keyup.enter="handleDetect"
          />
          <span class="hint">RSS feed, API endpoint, or news page URL</span>
        </div>

        <div v-if="detectError" class="error-message">
          {{ detectError }}
        </div>

        <div class="modal-actions">
          <button class="btn-secondary" @click="$emit('close')">Cancel</button>
          <button
            class="btn-primary"
            :disabled="!isValidUrl || detecting"
            @click="handleDetect"
          >
            <span v-if="detecting">Detecting...</span>
            <span v-else>Detect Source</span>
          </button>
        </div>
      </div>

      <!-- Step 2: Configuration -->
      <div v-else class="modal-body">
        <!-- Detection result -->
        <div v-if="detectResult" class="detect-result">
          <div class="detect-badge" :class="detectResult.detected_type">
            {{ getTypeLabel(detectResult.detected_type) }}
          </div>
          <span class="confidence">
            Confidence: {{ getConfidenceLabel(detectResult.confidence) }}
            ({{ Math.round(detectResult.confidence * 100) }}%)
          </span>
        </div>

        <!-- Preview items -->
        <div v-if="detectResult?.preview_items?.length" class="preview-section">
          <h4>Preview</h4>
          <div class="preview-list">
            <div v-for="(item, i) in detectResult.preview_items.slice(0, 3)" :key="i" class="preview-item">
              <span class="preview-title">{{ item.title || 'Untitled' }}</span>
            </div>
          </div>
        </div>

        <div class="form-group">
          <label for="name">Source Name</label>
          <input
            id="name"
            v-model="name"
            type="text"
            class="input"
            placeholder="My News Source"
            required
          />
        </div>

        <div class="form-group">
          <label for="type">Source Type</label>
          <select id="type" v-model="sourceType" class="input">
            <option value="rss">RSS Feed</option>
            <option value="api">JSON API</option>
            <option value="html">HTML Scraping</option>
          </select>
        </div>

        <div class="form-group">
          <label for="description">Description (optional)</label>
          <input
            id="description"
            v-model="description"
            type="text"
            class="input"
            placeholder="Brief description"
          />
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="tags">Tags (comma-separated)</label>
            <input
              id="tags"
              v-model="tags"
              type="text"
              class="input"
              placeholder="tech, news, china"
            />
          </div>

          <div class="form-group">
            <label for="refresh">Refresh Interval</label>
            <select id="refresh" v-model="refreshInterval" class="input">
              <option :value="5">5 minutes</option>
              <option :value="15">15 minutes</option>
              <option :value="30">30 minutes</option>
              <option :value="60">1 hour</option>
              <option :value="360">6 hours</option>
              <option :value="1440">24 hours</option>
            </select>
          </div>
        </div>

        <div v-if="sourceStore.error" class="error-message">
          {{ sourceStore.error }}
        </div>

        <div class="modal-actions">
          <button class="btn-secondary" @click="handleBack">Back</button>
          <button
            class="btn-primary"
            :disabled="!name || sourceStore.loading"
            @click="handleCreate"
          >
            <span v-if="sourceStore.loading">Creating...</span>
            <span v-else>Create Source</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
  padding: var(--space-4);
}

.modal {
  width: 100%;
  max-width: 500px;
  border-radius: var(--radius-2xl);
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-5) var(--space-6);
  border-bottom: 1px solid var(--glass-border);
}

.modal-header h2 {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  color: var(--color-neutral-800);
}

.close-btn {
  background: none;
  border: none;
  font-size: var(--text-2xl);
  color: var(--color-neutral-400);
  cursor: pointer;
  line-height: 1;
  padding: var(--space-1);
}

.close-btn:hover {
  color: var(--color-neutral-600);
}

.modal-body {
  padding: var(--space-6);
}

.step-description {
  color: var(--color-neutral-600);
  margin-bottom: var(--space-5);
}

.form-group {
  margin-bottom: var(--space-4);
}

.form-group label {
  display: block;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-neutral-700);
  margin-bottom: var(--space-2);
}

.hint {
  font-size: var(--text-xs);
  color: var(--color-neutral-400);
  margin-top: var(--space-1);
  display: block;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-4);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
  margin-top: var(--space-6);
  padding-top: var(--space-5);
  border-top: 1px solid var(--glass-border);
}

/* Detection result */
.detect-result {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-neutral-50);
  border-radius: var(--radius-lg);
  margin-bottom: var(--space-5);
}

.detect-badge {
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: 600;
  color: white;
}

.detect-badge.rss {
  background: linear-gradient(135deg, #f97316, #ea580c);
}

.detect-badge.api {
  background: linear-gradient(135deg, #3b82f6, #2563eb);
}

.detect-badge.html {
  background: linear-gradient(135deg, #8b5cf6, #7c3aed);
}

.confidence {
  font-size: var(--text-sm);
  color: var(--color-neutral-500);
}

/* Preview */
.preview-section {
  margin-bottom: var(--space-5);
}

.preview-section h4 {
  font-size: var(--text-sm);
  color: var(--color-neutral-600);
  margin-bottom: var(--space-2);
}

.preview-list {
  background: var(--color-neutral-50);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.preview-item {
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-neutral-100);
}

.preview-item:last-child {
  border-bottom: none;
}

.preview-title {
  font-size: var(--text-sm);
  color: var(--color-neutral-700);
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Error */
.error-message {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid var(--color-error);
  color: var(--color-error);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  margin-top: var(--space-4);
}
</style>
