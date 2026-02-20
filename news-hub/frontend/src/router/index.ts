import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      component: () => import('@/components/AppLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          name: 'home',
          component: () => import('@/views/NewsView.vue')
        },
        {
          path: 'sources',
          name: 'sources',
          component: () => import('@/views/SourcesView.vue')
        },
        {
          path: 'tags',
          name: 'tags',
          component: () => import('@/views/TagRulesView.vue')
        },
        {
          path: 'search',
          name: 'search',
          component: () => import('@/views/SearchView.vue')
        },
        {
          path: 'assistant',
          name: 'assistant',
          component: () => import('@/views/AssistantView.vue')
        },
        {
          path: 'assistant/search-workbench',
          name: 'assistant-search-workbench',
          component: () => import('@/views/AssistantSearchWorkbenchView.vue')
        },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('@/views/SettingsView.vue')
        }
      ]
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { guest: true }
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/RegisterView.vue'),
      meta: { guest: true }
    }
  ]
})

// Navigation guard
router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore()

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next({ name: 'login', query: { redirect: to.fullPath } })
  } else if (to.meta.guest && authStore.isAuthenticated) {
    next({ name: 'home' })
  } else {
    next()
  }
})

export default router
