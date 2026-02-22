<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
      <div class="article-modal-panel">
        <div class="modal-header">
          <h3 v-if="article">{{ article.title }}</h3>
          <h3 v-else-if="loading">加载中...</h3>
          <h3 v-else>文章详情</h3>
          <button class="modal-close" @click="$emit('close')">&times;</button>
        </div>

        <div class="modal-body">
          <!-- Loading -->
          <div v-if="loading" class="article-loading">
            <span class="spinner"></span>
            <span>正在加载文章...</span>
          </div>

          <!-- Error -->
          <div v-else-if="error" class="article-error">
            <p>{{ error }}</p>
            <button class="btn-retry" @click="fetchArticle">重试</button>
          </div>

          <!-- Article content -->
          <template v-else-if="article">
            <div class="article-meta">
              <span v-if="article.source_name" class="meta-source">
                {{ article.source_name }}
              </span>
              <span v-if="article.metadata?.author" class="meta-author">
                {{ article.metadata.author }}
              </span>
              <span v-if="article.published_at" class="meta-date">
                {{ formatDate(article.published_at) }}
              </span>
            </div>

            <img
              v-if="article.image_url"
              :src="article.proxied_image_url || article.image_url"
              :alt="article.title"
              class="article-cover"
              loading="lazy"
            />

            <div
              v-if="renderedHtml"
              class="article-content markdown-body"
              v-html="renderedHtml"
            ></div>
            <p v-else class="article-empty">暂无正文内容</p>
          </template>
        </div>

        <div v-if="article" class="modal-footer">
          <a :href="article.url" target="_blank" rel="noopener" class="btn-original">
            查看原文 ↗
          </a>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { marked } from 'marked'
import { newsApi, type NewsItem } from '@/api/news'

const props = defineProps<{
  visible: boolean
  newsId: string
}>()

defineEmits<{ close: [] }>()

const article = ref<NewsItem | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

watch(
  () => [props.visible, props.newsId],
  ([vis, id]) => {
    if (vis && id) fetchArticle()
  },
  { immediate: true },
)

async function fetchArticle() {
  if (!props.newsId) return
  loading.value = true
  error.value = null
  article.value = null
  try {
    const resp = await newsApi.get(props.newsId)
    article.value = resp.data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

const renderedHtml = computed(() => {
  const content = article.value?.content
  if (!content) return ''
  return marked.parse(content, { async: false }) as string
})

function formatDate(dateStr: string) {
  const d = new Date(dateStr)
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
}
</script>

<style scoped>
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.55); z-index: 1000; display: flex; align-items: center; justify-content: center; padding: var(--space-4, 16px); }
.article-modal-panel { background: var(--color-neutral-0, #fff); border-radius: var(--radius-xl, 12px); width: 100%; max-width: 780px; max-height: 90vh; display: flex; flex-direction: column; box-shadow: var(--shadow-xl, 0 20px 60px rgba(0,0,0,0.3)); }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: var(--space-4, 16px) var(--space-5, 20px); border-bottom: 1px solid var(--color-neutral-200, #e5e7eb); flex-shrink: 0; }
.modal-header h3 { font-size: var(--text-lg, 18px); font-weight: 600; color: var(--color-neutral-800, #1f2937); margin: 0; line-height: 1.4; flex: 1; margin-right: 12px; }
.modal-close { background: none; border: none; font-size: 24px; color: var(--color-neutral-400, #9ca3af); cursor: pointer; line-height: 1; padding: 0 4px; flex-shrink: 0; }
.modal-close:hover { color: var(--color-neutral-700, #374151); }
.modal-body { padding: var(--space-5, 20px); overflow-y: auto; flex: 1; min-height: 0; }
.modal-footer { padding: var(--space-3, 12px) var(--space-5, 20px); border-top: 1px solid var(--color-neutral-200, #e5e7eb); flex-shrink: 0; display: flex; justify-content: flex-end; }

.article-loading { display: flex; align-items: center; gap: 10px; color: var(--color-neutral-500, #6b7280); padding: 40px 0; justify-content: center; }
.spinner { width: 20px; height: 20px; border: 2px solid var(--color-neutral-300, #d1d5db); border-top-color: var(--color-primary, #3b82f6); border-radius: 50%; animation: spin 0.6s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.article-error { text-align: center; padding: 40px 0; color: var(--color-danger, #ef4444); }
.btn-retry { margin-top: 12px; padding: 6px 16px; border: 1px solid var(--color-neutral-300, #d1d5db); border-radius: 6px; background: none; cursor: pointer; color: var(--color-neutral-600, #4b5563); }
.btn-retry:hover { background: var(--color-neutral-100, #f3f4f6); }

.article-meta { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; font-size: var(--text-sm, 14px); color: var(--color-neutral-500, #6b7280); }
.meta-source { font-weight: 500; color: var(--color-primary, #3b82f6); }

.article-cover { width: 100%; max-height: 360px; object-fit: cover; border-radius: 8px; margin-bottom: 20px; }

.article-empty { color: var(--color-neutral-400, #9ca3af); text-align: center; padding: 40px 0; }

.btn-original { display: inline-block; padding: 6px 16px; font-size: var(--text-sm, 14px); color: var(--color-primary, #3b82f6); border: 1px solid var(--color-primary, #3b82f6); border-radius: 6px; text-decoration: none; transition: all 0.15s; }
.btn-original:hover { background: var(--color-primary, #3b82f6); color: #fff; }

/* Markdown body styles */
.markdown-body { font-size: 15px; line-height: 1.75; color: var(--color-neutral-700, #374151); word-break: break-word; }
.markdown-body :deep(h1) { font-size: 1.5em; font-weight: 700; margin: 1.2em 0 0.6em; color: var(--color-neutral-800, #1f2937); }
.markdown-body :deep(h2) { font-size: 1.3em; font-weight: 600; margin: 1em 0 0.5em; color: var(--color-neutral-800, #1f2937); }
.markdown-body :deep(h3) { font-size: 1.1em; font-weight: 600; margin: 0.8em 0 0.4em; }
.markdown-body :deep(p) { margin: 0.8em 0; }
.markdown-body :deep(img) { max-width: 100%; border-radius: 6px; margin: 12px 0; }
.markdown-body :deep(a) { color: var(--color-primary, #3b82f6); text-decoration: none; }
.markdown-body :deep(a:hover) { text-decoration: underline; }
.markdown-body :deep(blockquote) { border-left: 3px solid var(--color-neutral-300, #d1d5db); padding-left: 16px; margin: 12px 0; color: var(--color-neutral-500, #6b7280); }
.markdown-body :deep(code) { background: var(--color-neutral-100, #f3f4f6); padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
.markdown-body :deep(pre) { background: var(--color-neutral-100, #f3f4f6); padding: 16px; border-radius: 8px; overflow-x: auto; margin: 12px 0; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 24px; margin: 8px 0; }
.markdown-body :deep(li) { margin: 4px 0; }
.markdown-body :deep(hr) { border: none; border-top: 1px solid var(--color-neutral-200, #e5e7eb); margin: 20px 0; }
</style>
