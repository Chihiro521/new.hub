<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'

const logs = ref<string[]>([])
const isRunning = ref(false)
let interval: number | null = null

const MOCK_LOGS = [
  '[INFO] Starting crawler for source: 36Kr...',
  '[INFO] Fetching RSS feed from https://36kr.com/feed',
  '[DEBUG] Parsed 25 items from feed',
  '[INFO] Processing item: "DeepMind releases new Gemini model"',
  '[INFO] Auto-tagging: Applied tags [AI, LLM]',
  '[INFO] Saved news item: 65b3f...',
  '[INFO] Indexing to Elasticsearch...',
  '[SUCCESS] Source 36Kr updated successfully. +5 new items.',
  '[INFO] Scheduler sleeping for 60s...',
  '[INFO] Starting crawler for source: V2EX...',
  '[INFO] Fetching RSS feed from https://v2ex.com/index.xml',
  '[WARN] Request timed out, retrying (1/3)...',
  '[INFO] Retry successful.',
  '[DEBUG] No new items found for V2EX.',
]

function addLog() {
  const log = MOCK_LOGS[Math.floor(Math.random() * MOCK_LOGS.length)]
  const timestamp = new Date().toLocaleTimeString()
  logs.value.unshift(`[${timestamp}] ${log}`)
  
  if (logs.value.length > 50) {
    logs.value.pop()
  }
}

function startSimulation() {
  if (isRunning.value) return
  isRunning.value = true
  addLog() // Initial log
  interval = window.setInterval(addLog, 1500)
}

function stopSimulation() {
  isRunning.value = false
  if (interval) {
    clearInterval(interval)
    interval = null
  }
}

onMounted(() => {
  startSimulation()
})

onUnmounted(() => {
  stopSimulation()
})
</script>

<template>
  <div class="crawler-logs card glass">
    <div class="logs-header">
      <h3>Crawler Logs (Live)</h3>
      <div class="status-indicator" :class="{ active: isRunning }">
        <span class="dot"></span>
        {{ isRunning ? 'Running' : 'Paused' }}
      </div>
    </div>
    
    <div class="logs-container">
      <div v-for="(log, index) in logs" :key="index" class="log-entry">
        {{ log }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.crawler-logs {
  display: flex;
  flex-direction: column;
  height: 300px;
  overflow: hidden;
}

.logs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--glass-border);
}

.logs-header h3 {
  font-size: 1rem;
  color: var(--color-neutral-700);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8rem;
  color: var(--color-neutral-500);
}

.status-indicator.active {
  color: var(--color-success);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: currentColor;
}

.status-indicator.active .dot {
  animation: pulse 2s infinite;
}

.logs-container {
  flex: 1;
  overflow-y: auto;
  font-family: 'Fira Code', monospace;
  font-size: 0.85rem;
  display: flex;
  flex-direction: column-reverse; /* Newest at top? No, logs usually scroll down. But unshift makes newest top. */
  gap: 0.25rem;
}

.log-entry {
  color: var(--color-neutral-600);
  word-break: break-all;
}

/* Log Colors */
.log-entry:nth-child(odd) {
  background: rgba(0, 0, 0, 0.02);
}

[data-theme="dark"] .log-entry {
  color: var(--color-neutral-400);
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}
</style>
