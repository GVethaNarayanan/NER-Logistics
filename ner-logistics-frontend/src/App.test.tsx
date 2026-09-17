import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom'
import { App } from './App'
import { authApi } from './api/auth'
import * as client from './api/client'

// Mock the API calls
vi.mock('./api/auth', () => ({
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
    getMe: vi.fn(),
  }
}))

vi.mock('./api/infrastructure', () => ({
  infrastructureApi: {
    getRoads: async () => ({ items: [], total: 0, skip: 0, limit: 100 }),
    getRoadsBbox: async () => ({ type: "FeatureCollection", features: [], total_matched: 0 }),
    getBridges: async () => ({ items: [], total: 0, skip: 0, limit: 100 }),
    getDistrictConnectivity: async () => ({ roads: { total: 0 }, bridges: { total: 0 } }),
    getRegistry: async () => ({ states: [] }),
    getDistrictBoundary: async () => ({ type: "Feature", geometry: {}, properties: {} }),
    locateDistrict: async () => ({ district_id: null, district_name: null })
  }
}))

vi.mock('./components/dashboard/MapComponent', () => ({
  MapComponent: () => <div data-testid="mock-map-component">Mock Map</div>
}))

describe('Phase 2: App Shell, Routing & Auth', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    window.sessionStorage.clear()
    client.clearAuth()
  })

  it('renders the public shell correctly while logged out', async () => {
    // getMe fails to simulate logged out state
    vi.mocked(authApi.getMe).mockRejectedValue(new Error('Unauthorized'))

    render(<App />)

    // Shell branding
    expect(screen.getByText('NER Logistics')).toBeInTheDocument()

    // Public navigation should be accessible
    expect(screen.getByRole('link', { name: /home/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /routes/i })).toBeInTheDocument()
    
    // Auth controls
    expect(screen.getAllByText(/login/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/register/i).length).toBeGreaterThan(0)
  })

  it('successful login establishes authenticated state and redirects', async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: 'fake-access',
      refresh_token: 'fake-refresh',
      token_type: 'bearer',
      expires_in: 3600
    })
    
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: 1,
      username: 'testadmin',
      email: 'admin@test.com',
      role: 'admin',
      is_active: true,
      created_at: new Date().toISOString()
    })

    render(<App />)

    // Navigate to Login (assuming standard DOM routing mock)
    // Actually, in JSDOM we can just click the login link
    const loginLink = screen.getAllByRole('link', { name: /login/i })[0]
    fireEvent.click(loginLink)

    // Wait for Login page to render
    expect(await screen.findByRole('heading', { name: /welcome back/i })).toBeInTheDocument()

    const usernameInput = screen.getByLabelText(/username/i)
    const passwordInput = screen.getByLabelText(/password/i)
    const submitBtn = screen.getByRole('button', { name: /sign in/i })

    fireEvent.change(usernameInput, { target: { value: 'testadmin' } })
    fireEvent.change(passwordInput, { target: { value: 'password123' } })
    fireEvent.click(submitBtn)

    // Verify API was called
    await waitFor(() => {
      expect(authApi.login).toHaveBeenCalledWith(expect.objectContaining({ username: 'testadmin' }))
      expect(authApi.getMe).toHaveBeenCalled()
    })

    // Verify authenticated UI (role indicator & username)
    expect(await screen.findByText('testadmin')).toBeInTheDocument()
    expect(screen.getByText('admin')).toBeInTheDocument()
    
    // Verify tokens were stored
    expect(client.getAccessToken()).toBe('fake-access')
    expect(window.sessionStorage.getItem('refresh_token')).toBe('fake-refresh')
  })

  it('session restoration works if refresh token exists', async () => {
    window.sessionStorage.setItem('refresh_token', 'saved-refresh')
    
    // Mock the direct fetch call in AuthContext for restoration
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: 'new-access', refresh_token: 'new-refresh' })
    })
    globalThis.fetch = mockFetch

    vi.mocked(authApi.getMe).mockResolvedValue({
      id: 2,
      username: 'fieldworker',
      email: 'fw@test.com',
      role: 'field_official',
      is_active: true,
      created_at: new Date().toISOString()
    })

    render(<App />)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('/auth/refresh'), expect.any(Object))
      expect(authApi.getMe).toHaveBeenCalled()
    })

    expect(await screen.findByText('fieldworker')).toBeInTheDocument()
    expect(screen.getByText('field official')).toBeInTheDocument()
  })

  it('logout clears tokens and user state', async () => {
    // Start authenticated
    window.sessionStorage.setItem('refresh_token', 'saved-refresh')
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: 'new-access', refresh_token: 'new-refresh' })
    })
    globalThis.fetch = mockFetch

    vi.mocked(authApi.getMe).mockResolvedValue({
      id: 2,
      username: 'fieldworker',
      email: 'fw@test.com',
      role: 'field_official',
      is_active: true,
      created_at: new Date().toISOString()
    })

    render(<App />)
    
    // Wait for auth to settle
    expect(await screen.findByText('fieldworker')).toBeInTheDocument()
    
    // Click logout
    const logoutBtn = screen.getAllByText(/logout/i)[0]
    fireEvent.click(logoutBtn)

    await waitFor(() => {
      expect(screen.queryByText('fieldworker')).not.toBeInTheDocument()
    })

    expect(client.getAccessToken()).toBeNull()
    expect(window.sessionStorage.getItem('refresh_token')).toBeNull()
  })
})
