import React, { useState } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { cn } from '../lib/utils'
import { useTranslation } from 'react-i18next'
import { ErrorState } from '../components/shared/ErrorState'

export const Login: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const { login, isAuthenticated } = useAuth()
  const { t } = useTranslation()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<ApiError | Error | string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  // Redirect if already authenticated
  React.useEffect(() => {
    if (isAuthenticated) {
      navigate((location.state as any)?.from || '/', { replace: true })
    }
  }, [isAuthenticated, navigate, location])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsLoading(true)

    try {
      const tokens = await authApi.login({
        username,
        password,
        scope: '',
      })

      await login(tokens.access_token, tokens.refresh_token)
      // The useEffect will handle the redirect once AuthContext updates
    } catch (err: any) {
      if (err instanceof ApiError && err.code === 401) {
        setError(t('auth.invalid_credentials', 'Invalid username/email or password. Please check your credentials and try again.'))
      } else {
        setError(err)
      }
      setIsLoading(false)
    }
  }

  return (
    <div className="container mx-auto flex h-[calc(100vh-4rem)] w-screen flex-col items-center justify-center">
      <div className="mx-auto flex w-full flex-col justify-center space-y-6 sm:w-[350px]">
        <div className="flex flex-col space-y-2 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">{t('auth.login_title', 'Welcome back')}</h1>
          <p className="text-sm text-muted-foreground">
            {t('auth.login_subtitle', 'Enter your credentials to access your account')}
          </p>
        </div>

        <div className="grid gap-6">
          <form onSubmit={handleSubmit}>
            <div className="grid gap-4">
              <div className="grid gap-1">
                <label className="text-sm font-medium leading-none" htmlFor="username">
                  {t('auth.username', 'Username')}
                </label>
                <input
                  id="username"
                  placeholder="name@example.com or username"
                  autoCapitalize="none"
                  autoComplete="username"
                  autoCorrect="off"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={isLoading}
                  className={cn(
                    "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors",
                    "file:border-0 file:bg-transparent file:text-sm file:font-medium",
                    "placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                  )}
                />
              </div>
              <div className="grid gap-1">
                <label className="text-sm font-medium leading-none" htmlFor="password">
                  {t('auth.password', 'Password')}
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isLoading}
                  className={cn(
                    "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors",
                    "file:border-0 file:bg-transparent file:text-sm file:font-medium",
                    "placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                  )}
                />
              </div>

              {error && (
                <div className="mt-2">
                  <ErrorState error={error} />
                </div>
              )}

              <button
                type="submit"
                disabled={isLoading}
                className={cn(
                  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-semibold transition-colors",
                  "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                  "disabled:pointer-events-none disabled:opacity-50",
                  "bg-primary text-primary-foreground shadow hover:bg-primary/90 h-10 px-4 py-2"
                )}
              >
                {isLoading ? t('auth.signing_in', 'Signing In...') : t('auth.sign_in_button', 'Sign In')}
              </button>

              <div className="relative my-2">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-background px-2 text-muted-foreground font-semibold">
                    New to NER Logistics?
                  </span>
                </div>
              </div>

              <Link
                to="/register"
                className="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-semibold transition-colors border border-input bg-muted/40 hover:bg-muted text-foreground h-10 px-4 py-2 shadow-sm"
              >
                ✨ Create New Account (Register)
              </Link>
            </div>
          </form>
        </div>

        {/* Quick Demo Credentials for Reviewers */}
        <div className="p-3 bg-muted/40 border rounded-lg text-xs space-y-2">
          <p className="font-semibold text-muted-foreground text-center">⚡ Quick Demo Logins (1-Click Fill):</p>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => {
                setUsername('Vetha')
                setPassword('Vetha_2006')
              }}
              className="py-1.5 px-2 bg-background border hover:border-primary rounded text-[11px] font-medium text-left truncate transition-colors shadow-sm"
              title="Field Official: Vetha / Vetha_2006"
            >
              🧑‍💼 <span className="font-bold">Field Official</span>
            </button>
            <button
              type="button"
              onClick={() => {
                setUsername('admin')
                setPassword('admin123')
              }}
              className="py-1.5 px-2 bg-background border hover:border-primary rounded text-[11px] font-medium text-left truncate transition-colors shadow-sm"
              title="Admin: admin / admin123"
            >
              🛡️ <span className="font-bold">Administrator</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
