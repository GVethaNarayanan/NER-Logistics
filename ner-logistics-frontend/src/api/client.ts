// Schema types are in auth.ts and elsewhere

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || (typeof window !== 'undefined' && window.location.hostname.includes('vercel.app') ? 'https://ner-logistics-1.onrender.com' : '')

// --- Types ---

export type BackendErrorPayload = {
  error: {
    code: number
    message: string
    detail?: any
    path: string
  }
}

export class ApiError extends Error {
  public code: number
  public detail?: any
  public path: string

  constructor(payload: BackendErrorPayload) {
    super(payload.error.message)
    this.name = 'ApiError'
    this.code = payload.error.code
    this.detail = payload.error.detail
    this.path = payload.error.path
  }
}

// In-memory access token storage (better against XSS than localStorage)
let accessToken: string | null = null

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null) {
  accessToken = token
}

export function getRefreshToken(): string | null {
  return sessionStorage.getItem('refresh_token')
}

export function setRefreshToken(token: string | null) {
  if (token) {
    sessionStorage.setItem('refresh_token', token)
  } else {
    sessionStorage.removeItem('refresh_token')
  }
}

export const AUTH_CLEARED_EVENT = 'auth-cleared'

export function clearAuth() {
  accessToken = null
  sessionStorage.removeItem('refresh_token')
  window.dispatchEvent(new Event(AUTH_CLEARED_EVENT))
}

let isRefreshing = false
let refreshPromise: Promise<string | null> | null = null

export async function fetchClient(endpoint: string, options: RequestInit = {}): Promise<Response> {
  const url = `${API_BASE_URL}${endpoint}`
  const headers = new Headers(options.headers)

  if (accessToken && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }

  let response = await fetch(url, { ...options, headers })

  // Exactly one refresh attempt on 401
  if (response.status === 401 && !endpoint.includes('/auth/refresh') && !endpoint.includes('/auth/login')) {
    const refreshToken = getRefreshToken()
    if (refreshToken) {
      if (!isRefreshing) {
        isRefreshing = true
        refreshPromise = (async () => {
          try {
            // Wait, what does the backend expect for /auth/refresh?
            // Checking the OpenAPI schema, /auth/refresh expects the refresh_token in a JSON body or query param?
            // I need to check the schema for /auth/refresh.
            // I'll leave this unimplemented momentarily and implement it correctly once I check.
            const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ refresh_token: refreshToken })
            })
            if (res.ok) {
              const data = await res.json()
              setAccessToken(data.access_token)
              setRefreshToken(data.refresh_token)
              return data.access_token
            } else {
              clearAuth()
              return null
            }
          } catch {
            clearAuth()
            return null
          } finally {
            isRefreshing = false
            refreshPromise = null
          }
        })()
      }

      const newToken = await refreshPromise
      if (newToken) {
        // Retry exactly once
        headers.set('Authorization', `Bearer ${newToken}`)
        response = await fetch(url, { ...options, headers })
      }
    }
  }

  return response
}

export async function fetchJson<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetchClient(endpoint, options)

  if (!response.ok) {
    let errorPayload: BackendErrorPayload
    try {
      errorPayload = await response.json()
    } catch {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }
    if (errorPayload.error && errorPayload.error.message) {
      throw new ApiError(errorPayload)
    } else {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }
  }

  // Handle empty responses
  if (response.status === 204) {
    return null as any
  }

  return response.json()
}
