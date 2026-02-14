import apiClient from './client'
import type { ApiResponse } from './client'

// Types
export interface UserCreate {
  username: string
  email: string
  password: string
}

export interface UserLogin {
  username: string
  password: string
}

export interface UserResponse {
  id: string
  username: string
  email: string
  avatar_url: string | null
  settings: Record<string, unknown>
  created_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

// Auth API
export const authApi = {
  /**
   * Register a new user
   */
  async register(data: UserCreate): Promise<ApiResponse<UserResponse>> {
    const response = await apiClient.post<ApiResponse<UserResponse>>('/auth/register', data)
    return response.data
  },

  /**
   * Login and get JWT token
   */
  async login(data: UserLogin): Promise<ApiResponse<TokenResponse>> {
    const response = await apiClient.post<ApiResponse<TokenResponse>>('/auth/login', data)
    return response.data
  },

  /**
   * Get current user profile
   */
  async getMe(): Promise<ApiResponse<UserResponse>> {
    const response = await apiClient.get<ApiResponse<UserResponse>>('/auth/me')
    return response.data
  }
}
