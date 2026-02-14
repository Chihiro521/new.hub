<script setup lang="ts">
import { ref, computed } from 'vue'
import { useTagStore } from '@/stores/tags'
import type { TagRuleCreate } from '@/api/tags'

const emit = defineEmits(['close', 'added'])
const tagStore = useTagStore()

// Form State
const formData = ref<TagRuleCreate>({
  tag_name: '',
  keywords: [],
  match_mode: 'any',
  priority: 0,
  match_title: true,
  match_description: true,
  match_content: false,
  case_sensitive: false
})

// Keyword Management
const keywordInput = ref('')
const testText = ref('')
const extractedKeywords = ref<string[]>([])
const extracting = ref(false)

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

function addExtractedKeyword(kw: string) {
  if (!formData.value.keywords.includes(kw)) {
    formData.value.keywords.push(kw)
  }
}

async function handleExtract() {
  if (!testText.value.trim()) return
  
  extracting.value = true
  try {
    extractedKeywords.value = await tagStore.extractKeywords(testText.value)
  } finally {
    extracting.value = false
  }
}

// Submission
const isSubmitting = ref(false)
const error = ref<string | null>(null)

async function handleSubmit() {
  if (!formData.value.tag_name) {
    error.value = 'Tag name is required'
    return
  }
  if (formData.value.keywords.length === 0) {
    error.value = 'At least one keyword is required'
    return
  }

  isSubmitting.value = true
  error.value = null

  const result = await tagStore.createRule(formData.value)
  
  isSubmitting.value = false
  if (result) {
    emit('added')
  } else {
    error.value = tagStore.error
  }
}
</script>

<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal glass-strong">
      <div class="modal-header">
        <h3>Add Tag Rule</h3>
        <button class="close-btn" @click="$emit('close')">&times;</button>
      </div>

      <div class="modal-body">
        <!-- Error Message -->
        <div v-if="error" class="error-alert">
          {{ error }}
        </div>

        <div class="form-grid">
          <!-- Left Column: Basic Info -->
          <div class="col">
            <div class="form-group">
              <label>Tag Name</label>
              <input 
                v-model="formData.tag_name" 
                class="input" 
                placeholder="e.g. Technology" 
                autofocus
              />
            </div>

            <div class="form-group">
              <label>Match Mode</label>
              <div class="radio-group">
                <label class="radio">
                  <input type="radio" v-model="formData.match_mode" value="any" />
                  <span>Any Keyword</span>
                </label>
                <label class="radio">
                  <input type="radio" v-model="formData.match_mode" value="all" />
                  <span>All Keywords</span>
                </label>
              </div>
            </div>

            <div class="form-group">
              <label>Priority (0-100)</label>
              <input 
                type="number" 
                v-model="formData.priority" 
                class="input" 
                min="0" 
                max="100"
              />
            </div>

            <div class="form-group checkboxes">
              <label class="checkbox">
                <input type="checkbox" v-model="formData.match_title" />
                Match Title
              </label>
              <label class="checkbox">
                <input type="checkbox" v-model="formData.match_description" />
                Match Description
              </label>
              <label class="checkbox">
                <input type="checkbox" v-model="formData.match_content" />
                Match Content (Slower)
              </label>
              <label class="checkbox">
                <input type="checkbox" v-model="formData.case_sensitive" />
                Case Sensitive
              </label>
            </div>
          </div>

          <!-- Right Column: Keywords -->
          <div class="col">
            <div class="form-group">
              <label>Keywords</label>
              <div class="keyword-input-wrapper">
                <input 
                  v-model="keywordInput" 
                  class="input" 
                  placeholder="Type and press Enter" 
                  @keydown.enter.prevent="addKeyword"
                />
                <button class="btn-sm" @click="addKeyword">Add</button>
              </div>
              
              <div class="keywords-list">
                <span 
                  v-for="(kw, idx) in formData.keywords" 
                  :key="idx" 
                  class="keyword-chip"
                >
                  {{ kw }}
                  <button @click="removeKeyword(idx)">&times;</button>
                </span>
                <span v-if="formData.keywords.length === 0" class="placeholder">
                  No keywords added
                </span>
              </div>
            </div>

            <!-- Keyword Extraction Tool -->
            <div class="extraction-tool glass">
              <label>Keyword Helper</label>
              <p class="help-text">Paste text here to extract suggested keywords.</p>
              <textarea 
                v-model="testText" 
                class="input textarea" 
                rows="3"
                placeholder="Paste news content here..."
              ></textarea>
              <button 
                class="btn-sm btn-secondary full-width" 
                :disabled="extracting"
                @click="handleExtract"
              >
                {{ extracting ? 'Extracting...' : 'Extract Keywords' }}
              </button>

              <div v-if="extractedKeywords.length > 0" class="extracted-list">
                <p>Suggestions (Click to add):</p>
                <div class="chips">
                  <button 
                    v-for="kw in extractedKeywords" 
                    :key="kw"
                    class="suggestion-chip"
                    @click="addExtractedKeyword(kw)"
                  >
                    {{ kw }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn-secondary" @click="$emit('close')">Cancel</button>
        <button 
          class="btn-primary" 
          :disabled="isSubmitting"
          @click="handleSubmit"
        >
          {{ isSubmitting ? 'Creating...' : 'Create Rule' }}
        </button>
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
  max-width: 900px;
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xl);
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.modal-header {
  padding: var(--space-6);
  border-bottom: 1px solid var(--glass-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-header h3 {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  color: var(--color-neutral-800);
}

.close-btn {
  background: none;
  border: none;
  font-size: var(--text-2xl);
  color: var(--color-neutral-500);
  cursor: pointer;
  padding: 0 var(--space-2);
}

.modal-body {
  padding: var(--space-6);
  overflow-y: auto;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-8);
}

@media (max-width: 768px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}

.form-group {
  margin-bottom: var(--space-6);
}

.form-group label {
  display: block;
  font-weight: 600;
  color: var(--color-neutral-700);
  margin-bottom: var(--space-2);
}

.input {
  width: 100%;
}

.textarea {
  resize: vertical;
}

.radio-group {
  display: flex;
  gap: var(--space-6);
}

.radio {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
}

.checkboxes {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.checkbox {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
}

.keyword-input-wrapper {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.keywords-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  min-height: 40px;
  padding: var(--space-3);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.3);
}

.keyword-chip {
  background: var(--color-primary-100);
  color: var(--color-primary-700);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.keyword-chip button {
  background: none;
  border: none;
  color: var(--color-primary-500);
  cursor: pointer;
  font-weight: bold;
  padding: 0 2px;
}

.keyword-chip button:hover {
  color: var(--color-primary-800);
}

.placeholder {
  color: var(--color-neutral-400);
  font-style: italic;
}

/* Extraction Tool */
.extraction-tool {
  padding: var(--space-4);
  border-radius: var(--radius-lg);
  margin-top: var(--space-2);
}

.help-text {
  font-size: var(--text-xs);
  color: var(--color-neutral-500);
  margin-bottom: var(--space-2);
}

.full-width {
  width: 100%;
  margin-top: var(--space-2);
}

.extracted-list {
  margin-top: var(--space-4);
}

.extracted-list p {
  font-size: var(--text-xs);
  font-weight: 600;
  margin-bottom: var(--space-2);
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.suggestion-chip {
  background: var(--color-secondary-100);
  color: var(--color-secondary-700);
  border: 1px solid var(--color-secondary-200);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all 0.2s;
}

.suggestion-chip:hover {
  background: var(--color-secondary-200);
  transform: translateY(-1px);
}

.modal-footer {
  padding: var(--space-6);
  border-top: 1px solid var(--glass-border);
  display: flex;
  justify-content: flex-end;
  gap: var(--space-4);
}

.error-alert {
  background: var(--color-error);
  color: white;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  margin-bottom: var(--space-4);
}
</style>
