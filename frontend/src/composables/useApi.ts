import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios'
import { useRouter } from 'vue-router'

const TOKEN_KEY = 'excludr_token'

export function useApi() {
  const router = useRouter()

  const api: AxiosInstance = axios.create({
    baseURL: '/api/v1',
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

  // Response interceptor to handle 401
  api.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error.response?.status === 401) {
        localStorage.removeItem(TOKEN_KEY)
        router.push('/login')
      }
      return Promise.reject(error)
    }
  )

  const get = <T>(url: string, config?: AxiosRequestConfig) => {
    return api.get<T>(url, config).then((res) => res.data?.data || res.data)
  }

  const getRaw = <T>(url: string, config?: AxiosRequestConfig) => {
    return api.get<T>(url, config).then((res) => res.data)
  }

  const post = <T>(url: string, data?: any, config?: AxiosRequestConfig) => {
    return api.post<T>(url, data, config).then((res) => res.data?.data || res.data)
  }

  const patch = <T>(url: string, data?: any, config?: AxiosRequestConfig) => {
    return api.patch<T>(url, data, config).then((res) => res.data?.data || res.data)
  }

  const del = <T>(url: string, config?: AxiosRequestConfig) => {
    return api.delete<T>(url, config).then((res) => res.data?.data || res.data)
  }

  const setToken = (token: string) => {
    localStorage.setItem(TOKEN_KEY, token)
  }

  const getToken = () => {
    return localStorage.getItem(TOKEN_KEY)
  }

  const clearToken = () => {
    localStorage.removeItem(TOKEN_KEY)
  }

  return {
    api,
    get,
    getRaw,
    post,
    patch,
    delete: del,
    setToken,
    getToken,
    clearToken,
  }
}
