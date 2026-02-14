<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <div class="home-page">
    <!-- Background decoration -->
    <div class="bg-decoration">
      <div class="circle circle-1"></div>
      <div class="circle circle-2"></div>
    </div>

    <!-- Header -->
    <header class="header glass">
      <div class="header-left">
        <h1 class="logo gradient-text">News Hub</h1>
        <nav class="nav">
          <router-link to="/" class="nav-link active">Home</router-link>
          <router-link to="/sources" class="nav-link">Sources</router-link>
        </nav>
      </div>
      <div class="user-menu">
        <span class="username">{{ authStore.username }}</span>
        <button class="btn-secondary logout-btn" @click="handleLogout">
          Logout
        </button>
      </div>
    </header>

    <!-- Main content -->
    <main class="main-content">
      <div class="welcome-card card">
        <h2>Welcome, {{ authStore.username || 'User' }}!</h2>
        <p>Your personalized news hub is ready.</p>
        <router-link to="/sources" class="btn-primary action-btn">
          Manage Sources
        </router-link>
      </div>
    </main>
  </div>
</template>

<style scoped>
.home-page {
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
  opacity: 0.4;
}

.circle-1 {
  width: 600px;
  height: 600px;
  background: var(--color-primary-200);
  top: -200px;
  right: -200px;
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

/* Main content */
.main-content {
  padding: var(--space-8);
  max-width: 1200px;
  margin: 0 auto;
}

.welcome-card {
  text-align: center;
  max-width: 500px;
  margin: var(--space-16) auto;
}

.welcome-card h2 {
  font-family: var(--font-display);
  font-size: var(--text-3xl);
  color: var(--color-neutral-800);
  margin-bottom: var(--space-4);
}

.welcome-card p {
  color: var(--color-neutral-600);
  font-size: var(--text-lg);
  margin-bottom: var(--space-6);
}

.action-btn {
  display: inline-block;
  text-decoration: none;
}
</style>
