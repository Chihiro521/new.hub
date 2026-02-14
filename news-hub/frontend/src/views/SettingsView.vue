<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'

const router = useRouter()
const authStore = useAuthStore()
const themeStore = useThemeStore()

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <div class="settings-page">
    <!-- Header -->
    <header class="header glass">
      <div class="header-left">
        <h1 class="logo gradient-text">News Hub</h1>
        <nav class="nav">
          <router-link to="/" class="nav-link">Home</router-link>
          <router-link to="/sources" class="nav-link">Sources</router-link>
          <router-link to="/tags" class="nav-link">Tags</router-link>
          <router-link to="/search" class="nav-link">Search</router-link>
        </nav>
      </div>
      <div class="user-menu">
        <span class="username">{{ authStore.username }}</span>
        <button class="btn-secondary logout-btn" @click="handleLogout">Logout</button>
      </div>
    </header>

    <main class="main-content">
      <div class="page-header">
        <h2>Settings</h2>
        <p class="subtitle">Customize your experience</p>
      </div>

      <div class="settings-grid">
        <!-- Theme Section -->
        <section class="card glass">
          <h3>Theme Mode</h3>
          <p class="section-desc">Choose your preferred appearance.</p>
          
          <div class="options-group">
            <button 
              class="option-btn" 
              :class="{ active: themeStore.themeMode === 'light' }"
              @click="themeStore.setTheme('light')"
            >
              🌞 Light
            </button>
            <button 
              class="option-btn" 
              :class="{ active: themeStore.themeMode === 'dark' }"
              @click="themeStore.setTheme('dark')"
            >
              🌙 Dark
            </button>
            <button 
              class="option-btn" 
              :class="{ active: themeStore.themeMode === 'auto' }"
              @click="themeStore.setTheme('auto')"
            >
              🤖 Auto
            </button>
          </div>
        </section>

        <!-- Wallpaper Section -->
        <section class="card glass">
          <h3>Wallpaper</h3>
          <p class="section-desc">Enable animated background effects.</p>
          
          <div class="options-group">
            <button 
              class="option-btn" 
              :class="{ active: themeStore.wallpaperMode === 'dynamic' }"
              @click="themeStore.setWallpaper('dynamic')"
            >
              ✨ Dynamic
            </button>
            <button 
              class="option-btn" 
              :class="{ active: themeStore.wallpaperMode === 'static' }"
              @click="themeStore.setWallpaper('static')"
            >
              🖼️ Static
            </button>
            <button 
              class="option-btn" 
              :class="{ active: themeStore.wallpaperMode === 'disabled' }"
              @click="themeStore.setWallpaper('disabled')"
            >
              🚫 Disabled
            </button>
          </div>
        </section>
      </div>
    </main>
  </div>
</template>

<style scoped>
.settings-page {
  min-height: 100vh;
}

/* Header (Shared with other pages) */
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

.user-menu {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.username {
  color: var(--color-neutral-600);
  font-weight: 500;
}

.logout-btn {
  padding: 0.5rem 1rem;
  font-size: 0.9rem;
}

/* Main */
.main-content {
  max-width: 800px;
  margin: 3rem auto;
  padding: 0 1rem;
}

.page-header {
  margin-bottom: 2rem;
  text-align: center;
}

.subtitle {
  color: var(--color-neutral-500);
  margin-top: 0.5rem;
}

.settings-grid {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.section-desc {
  color: var(--color-neutral-500);
  margin-bottom: 1.5rem;
  font-size: 0.9rem;
}

.options-group {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
}

.option-btn {
  flex: 1;
  padding: 1rem;
  border: 1px solid var(--color-neutral-200);
  background: rgba(255, 255, 255, 0.5);
  border-radius: 0.75rem;
  cursor: pointer;
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-neutral-600);
  transition: all 0.2s;
}

.option-btn:hover {
  border-color: var(--color-primary-300);
  background: white;
}

.option-btn.active {
  background: var(--color-primary-100);
  border-color: var(--color-primary-400);
  color: var(--color-primary-700);
  box-shadow: 0 0 0 2px var(--color-primary-200);
}

[data-theme="dark"] .option-btn {
  background: rgba(0, 0, 0, 0.2);
  border-color: var(--color-neutral-700);
}

[data-theme="dark"] .option-btn.active {
  background: rgba(236, 72, 153, 0.2);
  border-color: var(--color-primary-600);
  color: var(--color-primary-300);
  box-shadow: 0 0 0 2px rgba(236, 72, 153, 0.2);
}
</style>
