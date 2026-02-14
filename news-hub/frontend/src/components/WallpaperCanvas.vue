<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useThemeStore } from '@/stores/theme'

const canvas = ref<HTMLCanvasElement | null>(null)
const themeStore = useThemeStore()
let ctx: CanvasRenderingContext2D | null = null
let animationId: number | null = null
let particles: Particle[] = []

interface Particle {
  x: number
  y: number
  radius: number
  speedX: number
  speedY: number
  color: string
  opacity: number
}

// Configuration
const PARTICLE_COUNT = 50
const COLORS_LIGHT = ['#fbcfe8', '#e9d5ff', '#fdf2f8', '#faf5ff']
const COLORS_DARK = ['#4a1d96', '#831843', '#312e81', '#1e1b4b']

function init() {
  if (!canvas.value) return
  ctx = canvas.value.getContext('2d')
  resize()
  createParticles()
  animate()
}

function resize() {
  if (!canvas.value) return
  canvas.value.width = window.innerWidth
  canvas.value.height = window.innerHeight
}

function createParticles() {
  particles = []
  const colors = themeStore.isDark ? COLORS_DARK : COLORS_LIGHT
  
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const radius = Math.random() * 80 + 20
    const x = Math.random() * (window.innerWidth + radius * 2) - radius
    const y = Math.random() * (window.innerHeight + radius * 2) - radius
    
    particles.push({
      x,
      y,
      radius,
      speedX: (Math.random() - 0.5) * 0.5,
      speedY: (Math.random() - 0.5) * 0.5,
      color: colors[Math.floor(Math.random() * colors.length)],
      opacity: Math.random() * 0.3 + 0.1
    })
  }
}

function animate() {
  if (!ctx || !canvas.value || themeStore.wallpaperMode !== 'dynamic') return
  
  ctx.clearRect(0, 0, canvas.value.width, canvas.value.height)
  
  particles.forEach(p => {
    // Move
    p.x += p.speedX
    p.y += p.speedY
    
    // Wrap around screen
    if (p.x < -p.radius * 2) p.x = canvas.value!.width + p.radius
    if (p.x > canvas.value!.width + p.radius * 2) p.x = -p.radius
    if (p.y < -p.radius * 2) p.y = canvas.value!.height + p.radius
    if (p.y > canvas.value!.height + p.radius * 2) p.y = -p.radius
    
    // Draw
    ctx!.beginPath()
    ctx!.arc(p.x, p.y, p.radius, 0, Math.PI * 2)
    ctx!.fillStyle = p.color
    ctx!.globalAlpha = p.opacity
    ctx!.fill()
  })
  
  animationId = requestAnimationFrame(animate)
}

watch(() => themeStore.isDark, () => {
  createParticles()
})

watch(() => themeStore.wallpaperMode, (val) => {
  if (val === 'dynamic') {
    if (!animationId) animate()
  } else {
    if (animationId) {
      cancelAnimationFrame(animationId)
      animationId = null
    }
    if (ctx && canvas.value) {
      ctx.clearRect(0, 0, canvas.value.width, canvas.value.height)
    }
  }
})

onMounted(() => {
  init()
  window.addEventListener('resize', resize)
})

onUnmounted(() => {
  if (animationId) cancelAnimationFrame(animationId)
  window.removeEventListener('resize', resize)
})
</script>

<template>
  <canvas ref="canvas" class="wallpaper-canvas"></canvas>
</template>

<style scoped>
.wallpaper-canvas {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  pointer-events: none;
  z-index: -2; /* Behind everything */
}
</style>
