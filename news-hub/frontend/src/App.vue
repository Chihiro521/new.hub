<script setup lang="ts">
import { RouterView } from 'vue-router'
import WallpaperCanvas from '@/components/WallpaperCanvas.vue'
import { useThemeStore } from '@/stores/theme'

// Initialize theme store
const themeStore = useThemeStore()
</script>

<template>
  <WallpaperCanvas v-if="themeStore.wallpaperMode === 'dynamic'" />
  <RouterView />
</template>

<style scoped>
</style>
