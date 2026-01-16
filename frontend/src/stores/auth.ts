import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useApi } from '@/composables/useApi'
import type { User, LoginCredentials, RegisterData, TokenResponse } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const { get, post, setToken, clearToken, getToken } = useApi()

  const user = ref<User | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const isAuthenticated = computed(() => !!user.value && !!getToken())

  const login = async (credentials: LoginCredentials) => {
    loading.value = true
    error.value = null

    try {
      // API expects form data for /auth/token
      const formData = new URLSearchParams()
      formData.append('username', credentials.username)
      formData.append('password', credentials.password)

      const response = await post<TokenResponse>('/auth/token', formData, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
      })

      setToken(response.access_token)
      await fetchCurrentUser()
      return true
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Login failed'
      return false
    } finally {
      loading.value = false
    }
  }

  const register = async (data: RegisterData) => {
    loading.value = true
    error.value = null

    try {
      const newUser = await post<User>('/auth/register', data)
      // After registration, automatically log in
      await login({ username: data.email, password: data.password })
      return true
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Registration failed'
      return false
    } finally {
      loading.value = false
    }
  }

  const fetchCurrentUser = async () => {
    try {
      user.value = await get<User>('/users/me')
    } catch (err: any) {
      error.value = err.response?.data?.detail || 'Failed to fetch user'
      clearToken()
      user.value = null
    }
  }

  const logout = () => {
    clearToken()
    user.value = null
  }

  const initialize = async () => {
    if (getToken()) {
      await fetchCurrentUser()
    }
  }

  return {
    user,
    loading,
    error,
    isAuthenticated,
    login,
    register,
    logout,
    initialize,
  }
})
