<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const showPassword = ref(false)
const localError = ref('')

async function handleRegister() {
  localError.value = ''
  
  // Validate password match
  if (password.value !== confirmPassword.value) {
    localError.value = '两次输入的密码不一致'
    return
  }

  // Validate password length
  if (password.value.length < 6) {
    localError.value = '密码至少需要6个字符'
    return
  }

  const success = await authStore.register(username.value, email.value, password.value)
  if (success) {
    router.push('/')
  }
}

function goToLogin() {
  router.push('/login')
}
</script>

<template>
  <div class="auth-page">
    <!-- Background decoration -->
    <div class="bg-decoration">
      <div class="circle circle-1"></div>
      <div class="circle circle-2"></div>
      <div class="circle circle-3"></div>
    </div>

    <!-- Register card -->
    <div class="auth-card glass-strong">
      <div class="auth-header">
        <h1 class="gradient-text">News Hub</h1>
        <p class="subtitle">创建你的账号</p>
      </div>

      <form class="auth-form" @submit.prevent="handleRegister">
        <!-- Error message -->
        <div v-if="authStore.error || localError" class="error-message">
          {{ localError || authStore.error }}
          <button type="button" class="error-close" @click="localError = ''; authStore.clearError()">x</button>
        </div>

        <!-- Username -->
        <div class="form-group">
          <label for="username">用户名</label>
          <input
            id="username"
            v-model="username"
            type="text"
            class="input"
            placeholder="请选择一个用户名"
            required
            autocomplete="username"
            minlength="3"
            maxlength="32"
            pattern="[a-zA-Z0-9_]+"
          />
          <span class="hint">3-32个字符，支持字母、数字、下划线</span>
        </div>

        <!-- Email -->
        <div class="form-group">
          <label for="email">邮箱</label>
          <input
            id="email"
            v-model="email"
            type="email"
            class="input"
            placeholder="请输入邮箱"
            required
            autocomplete="email"
          />
        </div>

        <!-- Password -->
        <div class="form-group">
          <label for="password">密码</label>
          <div class="password-wrapper">
            <input
              id="password"
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              class="input"
              placeholder="请创建密码"
              required
              autocomplete="new-password"
              minlength="6"
            />
            <button
              type="button"
              class="password-toggle"
              @click="showPassword = !showPassword"
            >
              {{ showPassword ? '隐藏' : '显示' }}
            </button>
          </div>
          <span class="hint">至少6个字符</span>
        </div>

        <!-- Confirm Password -->
        <div class="form-group">
          <label for="confirmPassword">确认密码</label>
          <input
            id="confirmPassword"
            v-model="confirmPassword"
            :type="showPassword ? 'text' : 'password'"
            class="input"
            placeholder="请再次输入密码"
            required
            autocomplete="new-password"
          />
        </div>

        <!-- Submit -->
        <button
          type="submit"
          class="btn-primary submit-btn"
          :disabled="authStore.loading"
        >
          <span v-if="authStore.loading">创建中...</span>
          <span v-else>创建账号</span>
        </button>
      </form>

      <!-- Footer -->
      <div class="auth-footer">
        <p>
          已有账号？
          <button type="button" class="link-btn" @click="goToLogin">
            登录
          </button>
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-4);
  position: relative;
  overflow: hidden;
}

/* Background circles */
.bg-decoration {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: -1;
}

.circle {
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
  opacity: 0.6;
}

.circle-1 {
  width: 400px;
  height: 400px;
  background: var(--color-secondary-300);
  top: -100px;
  left: -100px;
  animation: float 8s ease-in-out infinite;
}

.circle-2 {
  width: 300px;
  height: 300px;
  background: var(--color-primary-300);
  bottom: -50px;
  right: -50px;
  animation: float 10s ease-in-out infinite reverse;
}

.circle-3 {
  width: 200px;
  height: 200px;
  background: var(--color-accent-400);
  top: 40%;
  right: 30%;
  animation: pulse 6s ease-in-out infinite;
}

@keyframes float {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-30px); }
}

@keyframes pulse {
  0%, 100% { opacity: 0.4; transform: scale(1); }
  50% { opacity: 0.6; transform: scale(1.1); }
}

/* Card */
.auth-card {
  width: 100%;
  max-width: 420px;
  padding: var(--space-8);
  border-radius: var(--radius-2xl);
  box-shadow: var(--shadow-xl);
}

.auth-header {
  text-align: center;
  margin-bottom: var(--space-6);
}

.auth-header h1 {
  font-family: var(--font-display);
  font-size: var(--text-4xl);
  font-weight: 700;
  margin-bottom: var(--space-2);
}

.subtitle {
  color: var(--color-neutral-500);
  font-size: var(--text-lg);
}

/* Form */
.auth-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.form-group label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-neutral-700);
}

.hint {
  font-size: var(--text-xs);
  color: var(--color-neutral-400);
}

.password-wrapper {
  position: relative;
}

.password-toggle {
  position: absolute;
  right: var(--space-3);
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--color-primary-500);
  font-size: var(--text-sm);
  cursor: pointer;
  padding: var(--space-1) var(--space-2);
}

.password-toggle:hover {
  color: var(--color-primary-600);
}

.submit-btn {
  width: 100%;
  padding: var(--space-4);
  font-size: var(--text-base);
  margin-top: var(--space-2);
}

.submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
  transform: none;
}

/* Error message */
.error-message {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid var(--color-error);
  color: var(--color-error);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.error-close {
  background: none;
  border: none;
  color: var(--color-error);
  cursor: pointer;
  font-size: var(--text-lg);
  line-height: 1;
  padding: 0 var(--space-1);
}

/* Footer */
.auth-footer {
  margin-top: var(--space-6);
  text-align: center;
  color: var(--color-neutral-500);
  font-size: var(--text-sm);
}

.link-btn {
  background: none;
  border: none;
  color: var(--color-primary-500);
  font-weight: 600;
  cursor: pointer;
  padding: 0;
}

.link-btn:hover {
  color: var(--color-primary-600);
  text-decoration: underline;
}
</style>
