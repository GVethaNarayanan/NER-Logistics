import React, { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { authApi, UserOut } from '../api/auth'
import { getRefreshToken, setAccessToken, setRefreshToken, clearAuth, API_BASE_URL, AUTH_CLEARED_EVENT } from '../api/client'

interface AuthContextType {
  user: UserOut | null
  role: string | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (accessToken: string, refreshToken: string) => Promise<void>
  logout: () => void
  restoreSession: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserOut | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const logout = useCallback(() => {
    clearAuth()
    setUser(null)
  }, [])

  const login = useCallback(async (accessToken: string, refreshToken: string) => {
    setAccessToken(accessToken)
    setRefreshToken(refreshToken)
    try {
      const me = await authApi.getMe()
      setUser(me)
    } catch (err) {
      logout()
      throw err
    }
  }, [logout])

  const restoreSession = useCallback(async () => {
    setIsLoading(true)
    const refreshToken = getRefreshToken()
    
    if (!refreshToken) {
      setIsLoading(false)
      return
    }

    try {
      // Direct fetch to avoid the client interceptor loop for initial bootstrap
      const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken })
      })

      if (res.ok) {
        const data = await res.json()
        setAccessToken(data.access_token)
        setRefreshToken(data.refresh_token)
        
        const me = await authApi.getMe()
        setUser(me)
      } else {
        logout()
      }
    } catch (error) {
      logout()
    } finally {
      setIsLoading(false)
    }
  }, [logout])

  useEffect(() => {
    restoreSession()
  }, [restoreSession])

  // Optional: Global listener for API 401 unrecoverable events could go here if needed,
  // but the client.ts already clears auth state. We just sync it here if it happens.
  // A simple way is to check getRefreshToken() periodically or rely on component renders.
  // Actually, client.ts handles its own state, but AuthContext drives the UI.
  // Let's ensure if client.ts clears tokens, we reflect it.
  useEffect(() => {
    const handleAuthCleared = () => setUser(null)
    window.addEventListener(AUTH_CLEARED_EVENT, handleAuthCleared)
    return () => window.removeEventListener(AUTH_CLEARED_EVENT, handleAuthCleared)
  }, [])

  const value: AuthContextType = {
    user,
    role: user?.role ?? null,
    isAuthenticated: !!user,
    isLoading,
    login,
    logout,
    restoreSession,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
