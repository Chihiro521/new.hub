<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import ChatFairy from '@/components/ChatFairy.vue'

const router = useRouter()
const authStore = useAuthStore()

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <div class="app-layout">
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
          <router-link to="/" class="nav-link">新闻</router-link>
          <router-link to="/sources" class="nav-link">订阅源</router-link>
          <router-link to="/tags" class="nav-link">标签</router-link>
          <router-link to="/search" class="nav-link">搜索</router-link>
          <router-link to="/assistant" class="nav-link">AI 助手</router-link>
          <router-link to="/settings" class="nav-link">设置</router-link>
        </nav>
      </div>
      <div class="user-menu">
        <span class="username">{{ authStore.username }}</span>
        <button class="btn-secondary logout-btn" @click="handleLogout">
          退出
        </button>
      </div>
    </header>

    <!-- Page Content -->
    <RouterView />

    <!-- AI Chat Fairy -->
    <ChatFairy />
  </div>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
  position: relative;
}

/* Background Decoration */
.bg-decoration {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
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

.nav-link.router-link-exact-active {
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

@media (max-width: 768px) {
  .header {
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-4);
  }

  .header-left {
    flex-direction: column;
    gap: var(--space-3);
  }

  .nav {
    flex-wrap: wrap;
    justify-content: center;
  }
}
</style>
