<script setup lang="ts">
defineProps({
  type: {
    type: String,
    default: 'text', // text, circle, rect, card
    validator: (value: string) => ['text', 'circle', 'rect', 'card'].includes(value)
  },
  width: {
    type: String,
    default: '100%'
  },
  height: {
    type: String,
    default: '1em'
  },
  count: {
    type: Number,
    default: 1
  }
})
</script>

<template>
  <div class="skeleton-wrapper">
    <div 
      v-for="i in count" 
      :key="i"
      class="skeleton" 
      :class="[type]"
      :style="{ width, height }"
    ></div>
  </div>
</template>

<style scoped>
.skeleton-wrapper {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.skeleton {
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.1) 25%,
    rgba(255, 255, 255, 0.2) 50%,
    rgba(255, 255, 255, 0.1) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
}

[data-theme="dark"] .skeleton {
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.05) 25%,
    rgba(255, 255, 255, 0.1) 50%,
    rgba(255, 255, 255, 0.05) 75%
  );
}

.skeleton.circle {
  border-radius: 50%;
  width: 3rem;
  height: 3rem;
}

.skeleton.rect {
  border-radius: 8px;
}

.skeleton.card {
  height: 200px;
  border-radius: 1rem;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
</style>
