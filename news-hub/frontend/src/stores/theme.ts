import { defineStore } from 'pinia'
import { ref, watch, computed } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'auto'
export type WallpaperMode = 'dynamic' | 'static' | 'disabled'

export const useThemeStore = defineStore('theme', () => {
  // State
  const themeMode = ref<ThemeMode>(
    (localStorage.getItem('theme_mode') as ThemeMode) || 'auto'
  )
  const wallpaperMode = ref<WallpaperMode>(
    (localStorage.getItem('wallpaper_mode') as WallpaperMode) || 'dynamic'
  )
  const systemDark = ref(window.matchMedia('(prefers-color-scheme: dark)').matches)

  // Computed
  const isDark = computed(() => {
    if (themeMode.value === 'auto') return systemDark.value
    return themeMode.value === 'dark'
  })

  // Watchers
  watch(themeMode, (val) => {
    localStorage.setItem('theme_mode', val)
    applyTheme()
  })

  watch(wallpaperMode, (val) => {
    localStorage.setItem('wallpaper_mode', val)
  })

  // System preference listener
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    systemDark.value = e.matches
    if (themeMode.value === 'auto') applyTheme()
  })

  // Actions
  function setTheme(mode: ThemeMode) {
    themeMode.value = mode
  }

  function setWallpaper(mode: WallpaperMode) {
    wallpaperMode.value = mode
  }

  function applyTheme() {
    const root = document.documentElement
    if (isDark.value) {
      root.classList.add('dark')
      root.setAttribute('data-theme', 'dark')
    } else {
      root.classList.remove('dark')
      root.setAttribute('data-theme', 'light')
    }
  }

  // Initialize
  applyTheme()

  return {
    themeMode,
    wallpaperMode,
    isDark,
    setTheme,
    setWallpaper,
    applyTheme
  }
})
