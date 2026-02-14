<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { searchApi } from '@/api/search'

const props = defineProps<{
  modelValue?: string
  placeholder?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
  (e: 'search', query: string): void
}>()

const router = useRouter()

const query = ref(props.modelValue || '')
const suggestions = ref<string[]>([])
const showSuggestions = ref(false)
const isLoading = ref(false)
const selectedIndex = ref(-1)

// Debounce timer
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const hasSuggestions = computed(() => suggestions.value.length > 0 && showSuggestions.value)

watch(() => props.modelValue, (val) => {
  query.value = val || ''
})

watch(query, (val) => {
  emit('update:modelValue', val)
  
  // Debounced autocomplete
  if (debounceTimer) clearTimeout(debounceTimer)
  
  if (val.length >= 2) {
    debounceTimer = setTimeout(() => {
      fetchSuggestions(val)
    }, 300)
  } else {
    suggestions.value = []
    showSuggestions.value = false
  }
})

async function fetchSuggestions(prefix: string) {
  if (prefix.length < 2) return
  
  isLoading.value = true
  try {
    const result = await searchApi.suggest(prefix, 5)
    if (result.code === 200) {
      suggestions.value = result.data.suggestions
      showSuggestions.value = suggestions.value.length > 0
      selectedIndex.value = -1
    }
  } catch {
    // Silently fail
  } finally {
    isLoading.value = false
  }
}

function handleSubmit() {
  if (!query.value.trim()) return
  
  showSuggestions.value = false
  emit('search', query.value.trim())
  
  // Navigate to search results
  router.push({
    path: '/search',
    query: { q: query.value.trim() }
  })
}

function selectSuggestion(suggestion: string) {
  query.value = suggestion
  showSuggestions.value = false
  handleSubmit()
}

function handleKeydown(event: KeyboardEvent) {
  if (!hasSuggestions.value) return
  
  switch (event.key) {
    case 'ArrowDown':
      event.preventDefault()
      selectedIndex.value = Math.min(selectedIndex.value + 1, suggestions.value.length - 1)
      break
    case 'ArrowUp':
      event.preventDefault()
      selectedIndex.value = Math.max(selectedIndex.value - 1, -1)
      break
    case 'Enter':
      if (selectedIndex.value >= 0) {
        event.preventDefault()
        selectSuggestion(suggestions.value[selectedIndex.value])
      }
      break
    case 'Escape':
      showSuggestions.value = false
      selectedIndex.value = -1
      break
  }
}

function handleFocus() {
  if (suggestions.value.length > 0) {
    showSuggestions.value = true
  }
}

function handleBlur() {
  // Delay to allow click on suggestions
  setTimeout(() => {
    showSuggestions.value = false
  }, 200)
}
</script>

<template>
  <div class="search-bar">
    <form @submit.prevent="handleSubmit" class="search-form">
      <div class="search-icon">🔍</div>
      <input
        v-model="query"
        type="text"
        class="search-input"
        :placeholder="placeholder || 'Search news...'"
        @keydown="handleKeydown"
        @focus="handleFocus"
        @blur="handleBlur"
        autocomplete="off"
      />
      <button 
        v-if="query" 
        type="button" 
        class="clear-btn"
        @click="query = ''; suggestions = []; showSuggestions = false"
      >
        ✕
      </button>
      <button type="submit" class="search-btn" :disabled="!query.trim()">
        Search
      </button>
    </form>

    <!-- Suggestions dropdown -->
    <Transition name="fade">
      <div v-if="hasSuggestions" class="suggestions">
        <div
          v-for="(suggestion, index) in suggestions"
          :key="suggestion"
          class="suggestion-item"
          :class="{ selected: index === selectedIndex }"
          @mousedown.prevent="selectSuggestion(suggestion)"
          @mouseenter="selectedIndex = index"
        >
          <span class="suggestion-icon">🔍</span>
          <span class="suggestion-text">{{ suggestion }}</span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.search-bar {
  position: relative;
  width: 100%;
  max-width: 600px;
}

.search-form {
  display: flex;
  align-items: center;
  background: white;
  border-radius: var(--radius-lg);
  border: 2px solid var(--color-neutral-200);
  padding: var(--space-2) var(--space-3);
  transition: all var(--transition-fast);
  box-shadow: var(--shadow-sm);
}

.search-form:focus-within {
  border-color: var(--color-primary-400);
  box-shadow: 0 0 0 3px rgba(168, 85, 247, 0.1);
}

.search-icon {
  font-size: var(--text-lg);
  margin-right: var(--space-2);
  opacity: 0.5;
}

.search-input {
  flex: 1;
  border: none;
  background: none;
  font-size: var(--text-base);
  color: var(--color-neutral-800);
  outline: none;
  padding: var(--space-1) 0;
}

.search-input::placeholder {
  color: var(--color-neutral-400);
}

.clear-btn {
  background: none;
  border: none;
  color: var(--color-neutral-400);
  cursor: pointer;
  padding: var(--space-1);
  font-size: var(--text-sm);
  margin-right: var(--space-2);
  transition: color var(--transition-fast);
}

.clear-btn:hover {
  color: var(--color-neutral-600);
}

.search-btn {
  background: var(--gradient-primary);
  color: white;
  border: none;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.search-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.search-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Suggestions */
.suggestions {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin-top: var(--space-2);
  background: white;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-neutral-200);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
  z-index: var(--z-dropdown);
}

.suggestion-item {
  display: flex;
  align-items: center;
  padding: var(--space-3) var(--space-4);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.suggestion-item:hover,
.suggestion-item.selected {
  background: var(--color-primary-50);
}

.suggestion-icon {
  font-size: var(--text-sm);
  margin-right: var(--space-3);
  opacity: 0.5;
}

.suggestion-text {
  color: var(--color-neutral-700);
  font-size: var(--text-sm);
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
