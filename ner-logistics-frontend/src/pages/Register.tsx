import React, { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { authApi } from '../api/auth'
import { ApiError } from '../api/client'
import { cn } from '../lib/utils'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { ErrorState } from '../components/shared/ErrorState'

export const Register: React.FC = () => {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { login } = useAuth()
  
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<ApiError | Error | string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setIsLoading(true)

    try {
      await authApi.register({
        username,
        email,
        password,
        role: 'field_official'
      })
      
      setIsSuccess(true)
      // Auto-login new user directly
      try {
        const tokens = await authApi.login({ username, password })
        await login(tokens.access_token, tokens.refresh_token)
        setTimeout(() => {
          navigate('/')
        }, 1200)
      } catch {
        setTimeout(() => {
          navigate('/login')
        }, 1500)
      }
    } catch (err: any) {
      setError(err)
      setIsLoading(false)
    }
  }

  if (isSuccess) {
    return (
      <div className="container mx-auto flex h-[calc(100vh-4rem)] w-screen flex-col items-center justify-center">
        <div className="mx-auto flex w-full flex-col justify-center space-y-6 sm:w-[350px] text-center">
          <div className="p-6 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 rounded-lg border border-emerald-500/20 shadow-sm">
            <h2 className="text-xl font-bold mb-2">🎉 Account Created Successfully!</h2>
            <p className="text-sm opacity-90">Signing you into NER Logistics...</p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto flex h-[calc(100vh-4rem)] w-screen flex-col items-center justify-center">
      <div className="mx-auto flex w-full flex-col justify-center space-y-6 sm:w-[350px]">
        <div className="flex flex-col space-y-2 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">{t('auth.register_title', 'Create an account')}</h1>
          <p className="text-sm text-muted-foreground">
            {t('auth.register_subtitle', 'Register as a field official')}
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
                  placeholder="johndoe"
                  autoCapitalize="none"
                  autoCorrect="off"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={isLoading}
                  className={cn(
                    "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors",
                    "placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                  )}
                />
              </div>

              <div className="grid gap-1">
                <label className="text-sm font-medium leading-none" htmlFor="email">
                  {t('auth.email', 'Email')}
                </label>
                <input
                  id="email"
                  type="email"
                  placeholder="name@example.com"
                  autoCapitalize="none"
                  autoCorrect="off"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={isLoading}
                  className={cn(
                    "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors",
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
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isLoading}
                  className={cn(
                    "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors",
                    "placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                  )}
                />
                <p className="text-xs text-muted-foreground mt-1">Must be at least 8 characters</p>
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
                  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors",
                  "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
                  "disabled:pointer-events-none disabled:opacity-50",
                  "bg-primary text-primary-foreground shadow hover:bg-primary/90 h-9 px-4 py-2 mt-2"
                )}
              >
                {isLoading ? t('auth.creating_account', 'Creating account...') : t('auth.register_button', 'Register')}
              </button>
            </div>
          </form>
        </div>

        <p className="px-8 text-center text-sm text-muted-foreground">
          {t('auth.have_account', 'Already have an account?')} {' '}
          <Link to="/login" className="underline underline-offset-4 hover:text-primary">
            {t('auth.sign_in_button', 'Sign In')}
          </Link>
        </p>
      </div>
    </div>
  )
}
