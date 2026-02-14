import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi, type UserResponse } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  // State
  const user = ref<UserResponse | null>(null)
  const token = ref<string | null>(localStorage.getItem('access_token'))
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Getters
  const isAuthenticated = computed(() => !!token.value)
  const username = computed(() => user.value?.username || '')

  // Actions
  async function login(username: string, password: string): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      const response = await authApi.login({ username, password })
      token.value = response.data.access_token
      localStorage.setItem('access_token', response.data.access_token)
      
      // Fetch user profile after login
      await fetchUser()
      return true
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Login failed'
      return false
    } finally {
      loading.value = false
    }
  }

  async function register(username: string, email: string, password: string): Promise<boolean> {
    loading.value = true
    error.value = null

    try {
      await authApi.register({ username, email, password })
      // Auto login after registration
      return await login(username, password)
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Registration failed'
      return false
    } finally {
      loading.value = false
    }
  }

  async function fetchUser(): Promise<void> {
    if (!token.value) return

    try {
      const response = await authApi.getMe()
      user.value = response.data
    } catch (e) {
      // Token invalid, logout
      logout()
    }
  }

  function logout(): void {
    user.value = null
    token.value = null
    localStorage.removeItem('access_token')
  }

  function clearError(): void {
    error.value = null
  }

  // Initialize: fetch user if token exists
  if (token.value) {
    fetchUser()
  }

  return {
    // State
    user,
    token,
    loading,
    error,
    // Getters
    isAuthenticated,
    username,
    // Actions
    login,
    register,
    fetchUser,
    logout,
    clearError
  }
})
