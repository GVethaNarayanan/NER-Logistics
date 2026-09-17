import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { Menu, X, User, Globe } from 'lucide-react'
import { cn } from '../../lib/utils'
import { useTranslation } from 'react-i18next'

export const Header: React.FC = () => {
  const { user, role, isAuthenticated, logout } = useAuth()
  const location = useLocation()
  const [isMobileMenuOpen, setIsMobileMenuOpen] = React.useState(false)
  const { t, i18n } = useTranslation()

  const navLinks = [
    { name: t('navigation.dashboard', 'Home'), path: '/' },
    { name: t('navigation.vehicles', 'Vehicles'), path: '/vehicles' },
    { name: t('navigation.incidents', 'Incidents'), path: '/incidents' },
    { name: t('navigation.alerts', 'Alerts'), path: '/alerts' },
    { name: t('navigation.saved_routes', 'Routes'), path: '/routes' },
  ]

  const toggleLanguage = () => {
    const nextLang = i18n.language === 'en' ? 'as' : 'en'
    i18n.changeLanguage(nextLang)
  }

  const isActive = (path: string) => location.pathname === path

  return (
    <header className="bg-background border-b sticky top-0 z-50">
      <div className="container mx-auto px-4 h-16 flex items-center justify-between">
        <div className="flex items-center gap-8">
          <Link to="/" className="font-bold text-xl text-primary shrink-0">
            NER Logistics
          </Link>
          
          {/* Desktop Nav */}
          <nav className="hidden md:flex items-center gap-6">
            {navLinks.map((link) => (
              <Link
                key={link.path}
                to={link.path}
                className={cn(
                  'text-sm font-medium transition-colors hover:text-primary',
                  isActive(link.path) ? 'text-primary' : 'text-muted-foreground'
                )}
              >
                {link.name}
              </Link>
            ))}
          </nav>
        </div>

        <div className="hidden md:flex items-center gap-4">
          <button
            onClick={toggleLanguage}
            className="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors px-2 py-1"
            title="Toggle Language"
            aria-label="Toggle Language"
          >
            <Globe className="w-4 h-4" />
            <span className="uppercase">{i18n.language}</span>
          </button>
          {isAuthenticated ? (
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2 text-sm text-muted-foreground bg-muted px-3 py-1.5 rounded-full">
                <User className="w-4 h-4" />
                <span className="font-medium text-foreground">{user?.username}</span>
                {role && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-bold bg-primary/10 text-primary border border-primary/20">
                    {role.replace('_', ' ')}
                  </span>
                )}
              </div>
              <button
                onClick={logout}
                className="text-sm font-medium text-muted-foreground hover:text-destructive transition-colors"
              >
                {t('navigation.sign_out', 'Logout')}
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-4">
              <Link
                to="/login"
                className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                {t('navigation.sign_in', 'Login')}
              </Link>
              <Link
                to="/register"
                className="text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 px-4 py-2 rounded-md transition-colors"
              >
                {t('auth.register_button', 'Register')}
              </Link>
            </div>
          )}
        </div>

        {/* Mobile menu button */}
        <button
          className="md:hidden p-2 text-muted-foreground hover:text-foreground"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
        >
          {isMobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
      </div>

      {/* Mobile Nav */}
      {isMobileMenuOpen && (
        <div className="md:hidden border-t bg-background">
          <nav className="flex flex-col p-4">
            <div className="flex justify-between items-center mb-4 px-4">
              <span className="text-sm font-medium text-muted-foreground">Language</span>
              <button
                onClick={toggleLanguage}
                className="flex items-center gap-2 text-sm font-medium text-foreground bg-muted px-3 py-1.5 rounded-md"
              >
                <Globe className="w-4 h-4" />
                <span className="uppercase">{i18n.language}</span>
              </button>
            </div>
            
            {navLinks.map((link) => (
              <Link
                key={link.path}
                to={link.path}
                onClick={() => setIsMobileMenuOpen(false)}
                className={cn(
                  'px-4 py-3 text-sm font-medium transition-colors hover:bg-muted rounded-md',
                  isActive(link.path) ? 'text-primary bg-primary/5' : 'text-muted-foreground'
                )}
              >
                {link.name}
              </Link>
            ))}
            
            <div className="my-2 border-t" />
            
            {isAuthenticated ? (
              <div className="flex flex-col gap-2 p-2">
                <div className="flex items-center gap-2 px-2 py-1">
                  <User className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm font-medium">{user?.username}</span>
                  {role && <span className="text-xs text-muted-foreground">({role})</span>}
                </div>
                <button
                  onClick={() => {
                    logout()
                    setIsMobileMenuOpen(false)
                  }}
                  className="px-4 py-2 text-sm font-medium text-left text-destructive hover:bg-destructive/10 rounded-md transition-colors"
                >
                  {t('navigation.sign_out', 'Logout')}
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-2 p-2">
                <Link
                  to="/login"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className="px-4 py-2 text-sm font-medium text-center hover:bg-muted rounded-md transition-colors"
                >
                  {t('navigation.sign_in', 'Login')}
                </Link>
                <Link
                  to="/register"
                  onClick={() => setIsMobileMenuOpen(false)}
                  className="px-4 py-2 text-sm font-medium text-center bg-primary text-primary-foreground hover:bg-primary/90 rounded-md transition-colors"
                >
                  {t('auth.register_button', 'Register')}
                </Link>
              </div>
            )}
          </nav>
        </div>
      )}
    </header>
  )
}
