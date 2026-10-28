import axios, {
  type AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'
import { useRouter } from 'vue-router'

const TOKEN_KEY = 'excludr_token'
const REFRESH_TOKEN_KEY = 'excludr_refresh_token'
const BASE_URL = '/api/v1'

type RetriableConfig = InternalAxiosRequestConfig & { _retry?: boolean }

// Shared across all useApi() instances so concurrent 401s trigger a single refresh
let refreshPromise: Promise<string> | null = null

const isAuthEndpoint = (url?: string) =>
  !!url && (url.includes('/auth/token') || url.includes('/auth/refresh'))

/** Exchange the stored refresh token for a new token pair. Rejects if it fails. */
const refreshAccessToken = (): Promise<string> => {
  if (!refreshPromise) {
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
    if (!refreshToken) return Promise.reject(new Error('No refresh token'))
    // Bare axios call: must not go through the interceptors below
    refreshPromise = axios
      .post<{ access_token: string; refresh_token: string }>(`${BASE_URL}/auth/refresh`, {
        refresh_token: refreshToken,
      })
      .then((res) => {
        localStorage.setItem(TOKEN_KEY, res.data.access_token)
        localStorage.setItem(REFRESH_TOKEN_KEY, res.data.refresh_token)
        return res.data.access_token
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

const clearTokens = () => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
}

export function useApi() {
  const router = useRouter()

  const api: AxiosInstance = axios.create({
    baseURL: BASE_URL,
    headers: {
      'Content-Type': 'application/json',
    },
  })

  // Request interceptor to add auth token
  api.interceptors.request.use(
    (config) => {
      const token = localStorage.getItem(TOKEN_KEY)
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
      return config
    },
    (error) => {
      return Promise.reject(error)
    }
  )

  // Response interceptor: on 401, refresh the access token once and retry the request
  api.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const original = error.config as RetriableConfig | undefined
      if (error.response?.status !== 401) return Promise.reject(error)

      if (original && !original._retry && !isAuthEndpoint(original.url)) {
        original._retry = true
        try {
          const newToken = await refreshAccessToken()
          original.headers.Authorization = `Bearer ${newToken}`
          return api(original)
        } catch {
          // fall through to logout
        }
      }

      if (!isAuthEndpoint(original?.url)) {
        clearTokens()
        router.push('/login')
      }
      return Promise.reject(error)
    }
  )

  // Backend may wrap payloads as { data: T }; unwrap when present
  const unwrap = <T>(body: unknown): T => {
    if (body && typeof body === 'object' && 'data' in body && (body as { data: unknown }).data) {
      return (body as { data: T }).data
    }
    return body as T
  }

  const get = <T>(url: string, config?: AxiosRequestConfig) => {
    return api.get<T>(url, config).then((res) => unwrap<T>(res.data))
  }

  const getRaw = <T>(url: string, config?: AxiosRequestConfig) => {
    return api.get<T>(url, config).then((res) => res.data)
  }

  const post = <T>(url: string, data?: any, config?: AxiosRequestConfig) => {
    return api.post<T>(url, data, config).then((res) => unwrap<T>(res.data))
  }

  const patch = <T>(url: string, data?: any, config?: AxiosRequestConfig) => {
    return api.patch<T>(url, data, config).then((res) => unwrap<T>(res.data))
  }

  const put = <T>(url: string, data?: any, config?: AxiosRequestConfig) => {
    return api.put<T>(url, data, config).then((res) => unwrap<T>(res.data))
  }

  const del = <T>(url: string, config?: AxiosRequestConfig) => {
    return api.delete<T>(url, config).then((res) => unwrap<T>(res.data))
  }

  const setToken = (token: string, refreshToken?: string) => {
    localStorage.setItem(TOKEN_KEY, token)
    if (refreshToken) {
      localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
    }
  }

  const getToken = () => {
    return localStorage.getItem(TOKEN_KEY)
  }

  const clearToken = () => {
    clearTokens()
  }

  return {
    api,
    get,
    getRaw,
    post,
    patch,
    put,
    delete: del,
    setToken,
    getToken,
    clearToken,
  }
}
