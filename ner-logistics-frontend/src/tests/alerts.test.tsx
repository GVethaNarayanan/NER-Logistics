import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import '@testing-library/jest-dom'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { Alerts } from '../pages/Alerts'
import { alertApi, AlertOut } from '../api/alerts'
import { AuthProvider } from '../contexts/AuthContext'
import { useAuth } from '../contexts/AuthContext'

vi.mock('../api/alerts', () => ({
  alertApi: {
    getAlerts: vi.fn(),
    createAlert: vi.fn()
  }
}))

vi.mock('../contexts/AuthContext', () => {
  return {
    AuthProvider: ({ children }: any) => <>{children}</>,
    useAuth: vi.fn(() => ({
      user: { id: 1, username: 'testuser', email: 'test@example.com', is_active: true, role: 'standard' },
      role: 'standard',
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      restoreSession: vi.fn()
    }))
  }
})

describe('Alerts Page (Phase 7)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(alertApi.getAlerts).mockResolvedValue({ items: [], total: 0, skip: 0, limit: 20 })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('renders alerts list and handles polling', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true }) // Allows testing-library waitFor to work with fake timers!
    const mockAlert: AlertOut = {
      id: 1,
      alert_type: 'general',
      severity: 'high',
      message_en: 'Test Alert 1',
      language: 'en',
      status: 'active',
      created_at: new Date().toISOString()
    }
    vi.mocked(alertApi.getAlerts).mockResolvedValue({ items: [mockAlert], total: 1, skip: 0, limit: 20 })

    render(
      <AuthProvider>
        <BrowserRouter>
          <Alerts />
        </BrowserRouter>
      </AuthProvider>
    )

    expect(alertApi.getAlerts).toHaveBeenCalledTimes(1)
    
    await waitFor(() => {
      expect(screen.getByText('Test Alert 1')).toBeInTheDocument()
    })

    // Advance timers by 30 seconds to trigger polling
    await vi.advanceTimersByTimeAsync(30000)
    
    expect(alertApi.getAlerts).toHaveBeenCalledTimes(2)
  })

  it('visually distinguishes active and resolved alerts', async () => {
    const activeAlert: AlertOut = {
      id: 1,
      alert_type: 'general',
      severity: 'high',
      message_en: 'Active Alert',
      language: 'en',
      status: 'active',
      created_at: new Date().toISOString()
    }
    const resolvedAlert: AlertOut = {
      id: 2,
      alert_type: 'weather',
      severity: 'low',
      message_en: 'Resolved Alert',
      language: 'en',
      status: 'resolved',
      created_at: new Date().toISOString(),
      resolved_at: new Date().toISOString()
    }

    vi.mocked(alertApi.getAlerts).mockResolvedValue({ items: [activeAlert, resolvedAlert], total: 2, skip: 0, limit: 20 })

    render(
      <AuthProvider>
        <BrowserRouter>
          <Alerts />
        </BrowserRouter>
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByText(/Active Alert/i)).toBeInTheDocument()
      expect(screen.getByText(/Resolved Alert/i)).toBeInTheDocument()
      expect(screen.getAllByText(/Resolved/i).length).toBeGreaterThan(0)
    })
    
    // Check severity label
    expect(screen.getByText('high')).toBeInTheDocument()
    expect(screen.getByText('low')).toBeInTheDocument()
  })

  it('displays message_local when provided', async () => {
    const bilingualAlert: AlertOut = {
      id: 1,
      alert_type: 'general',
      severity: 'medium',
      message_en: 'English Message',
      message_local: 'Local Translation',
      language: 'en',
      status: 'active',
      created_at: new Date().toISOString()
    }

    vi.mocked(alertApi.getAlerts).mockResolvedValue({ items: [bilingualAlert], total: 1, skip: 0, limit: 20 })

    render(
      <AuthProvider>
        <BrowserRouter>
          <Alerts />
        </BrowserRouter>
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByText('English Message')).toBeInTheDocument()
      // expect(screen.getByText('Local Translation')).toBeInTheDocument() // Removed because in Phase 8 we only show one language at a time.
    })
  })

  it('hides create button for standard users', async () => {
    render(
      <AuthProvider>
        <BrowserRouter>
          <Alerts />
        </BrowserRouter>
      </AuthProvider>
    )

    expect(screen.queryByText('New Alert')).not.toBeInTheDocument()
  })

  it('allows admins to open create form and submit new alert', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: 1, username: 'admin', email: 'admin@example.com', is_active: true, role: 'admin' },
      role: 'admin',
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      restoreSession: vi.fn()
    })

    const newAlert: AlertOut = {
      id: 99,
      alert_type: 'security',
      severity: 'high',
      message_en: 'Security Breach',
      language: 'en',
      status: 'active',
      created_at: new Date().toISOString()
    }
    vi.mocked(alertApi.createAlert).mockResolvedValue(newAlert)

    render(
      <AuthProvider>
        <BrowserRouter>
          <Alerts />
        </BrowserRouter>
      </AuthProvider>
    )

    // Admin should see New Alert button
    const createBtn = screen.getByText('New Alert')
    expect(createBtn).toBeInTheDocument()

    // Open modal
    fireEvent.click(createBtn)

    // Fill form
    fireEvent.change(screen.getByLabelText(/Type/i), { target: { value: 'security' } })
    fireEvent.change(screen.getByLabelText(/Severity/i), { target: { value: 'high' } })
    fireEvent.change(screen.getByLabelText(/Message \(English\)/i), { target: { value: 'Security Breach' } })

    // Submit
    fireEvent.click(screen.getByText('Create Alert'))

    await waitFor(() => {
      expect(alertApi.createAlert).toHaveBeenCalledWith({
        alert_type: 'security',
        severity: 'high',
        message_en: 'Security Breach',
        message_local: null,
        language: 'en',
        road_id: null,
        bridge_id: null
      })
      
      // Should auto-refresh after create
      expect(alertApi.getAlerts).toHaveBeenCalledTimes(2) 
    })
  })
})
