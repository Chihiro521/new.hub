import axios from 'axios'
import type { AxiosInstance, InternalAxiosRequestConfig, AxiosResponse } from 'axios'

// API Response type
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T
}

// Create axios instance
const apiClient: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// Request interceptor - add JWT token
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// Response interceptor - handle errors
apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    return response
  },
  (error) => {
    if (error.response) {
      const status = error.response.status
      
      // Handle 401 Unauthorized
      if (status === 401) {
        localStorage.removeItem('access_token')
        window.location.href = '/login'
      }
      
      // Extract error message
      const message = error.response.data?.detail || error.response.data?.message || 'Request failed'
      return Promise.reject(new Error(message))
    }
    
    return Promise.reject(error)
  }
)

export default apiClient
