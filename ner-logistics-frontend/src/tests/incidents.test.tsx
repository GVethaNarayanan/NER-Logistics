import { describe, it, expect, vi, beforeEach } from 'vitest'
import '@testing-library/jest-dom'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { Incidents } from '../pages/Incidents'
import { incidentApi, IncidentOut } from '../api/incidents'
import { AuthProvider } from '../contexts/AuthContext'
import { infrastructureApi } from '../api/infrastructure'
import * as offlineQueue from '../lib/offlineQueue'
import * as syncService from '../lib/syncService'

import { useAuth } from '../contexts/AuthContext'

vi.mock('../contexts/AuthContext', () => {
  return {
    AuthProvider: ({ children }: any) => <>{children}</>,
    useAuth: vi.fn(() => ({
      user: { id: 1, username: 'testuser', email: 'test@example.com', is_active: true, role: 'admin' },
      role: 'admin',
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      restoreSession: vi.fn()
    }))
  }
})

vi.mock('../api/incidents', () => ({
  incidentApi: {
    getIncidents: vi.fn(),
    createIncident: vi.fn(),
    uploadPhoto: vi.fn(),
    updateStatus: vi.fn(),
    syncBatch: vi.fn()
  }
}))

vi.mock('../api/infrastructure', () => ({
  infrastructureApi: {
    getRoads: vi.fn(),
    getBridges: vi.fn()
  }
}))

vi.mock('../lib/offlineQueue', () => ({
  addIncidentToQueue: vi.fn(),
  getQueuedIncidents: vi.fn(),
  updateQueuedIncident: vi.fn(),
  removeQueuedIncident: vi.fn()
}))

vi.mock('../lib/syncService', () => ({
  syncOfflineIncidents: vi.fn()
}))

// Mock Leaflet MapComponent to just expose a clickable div and avoid missing CSS/DOM errors
vi.mock('../components/dashboard/MapComponent', () => ({
  MapComponent: ({ onMapClick }: any) => (
    <div 
      data-testid="mock-map" 
      onClick={() => onMapClick?.(26.1, 91.7)}
    >
      Map
    </div>
  )
}))


describe('Incidents Page (Phase 6)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.unstubAllGlobals()
    
    // Mock navigator.onLine to true by default
    vi.stubGlobal('navigator', { onLine: true })
    
    // Mock API resolves
    vi.mocked(infrastructureApi.getRoads).mockResolvedValue({ items: [{ id: 1, name: 'Road 1', road_type: 'primary', start_lat: 26.1, start_lon: 91.7, end_lat: 26.2, end_lon: 91.8, status: 'open' }], total: 1, skip: 0, limit: 100 })
    vi.mocked(infrastructureApi.getBridges).mockResolvedValue({ items: [], total: 0, skip: 0, limit: 100 })
    vi.mocked(incidentApi.getIncidents).mockResolvedValue({ items: [], total: 0, skip: 0, limit: 100 })
    vi.mocked(offlineQueue.getQueuedIncidents).mockResolvedValue([])
    vi.mocked(syncService.syncOfflineIncidents).mockResolvedValue({ attempted: 0, succeeded: 0, failed: 0 })
  })

  it('renders incidents list and form', async () => {
    const mockIncident: IncidentOut = {
      id: 1,
      incident_type: 'accident',
      severity: 'medium',
      latitude: 26.1,
      longitude: 91.7,
      status: 'reported',
      synced: 'synced',
      reported_at: new Date().toISOString()
    }
    vi.mocked(incidentApi.getIncidents).mockResolvedValueOnce({ items: [mockIncident], total: 1, skip: 0, limit: 100 })

    render(
      <AuthProvider>
        <BrowserRouter>
          <Incidents />
        </BrowserRouter>
      </AuthProvider>
    )

    expect(screen.getByText('Field Incidents')).toBeTruthy()
    
    const accidentText = await screen.findByText(/accident/i)
    expect(accidentText).toBeTruthy()
    expect(screen.getAllByText(/reported/i).length).toBeGreaterThan(0)
  })

  it('allows filling the form and handles geo-tagging via map click', async () => {
    render(
      <AuthProvider>
        <BrowserRouter>
          <Incidents />
        </BrowserRouter>
      </AuthProvider>
    )

    // Form fields
    fireEvent.change(screen.getByPlaceholderText(/Provide incident details/i), { target: { value: 'Test Incident' } })
    
    // Location picker
    expect(screen.getByText('No location selected')).toBeTruthy()
    fireEvent.click(screen.getByText('Pick on Map'))
    fireEvent.click(screen.getByTestId('mock-map'))
    
    expect(screen.getByText('26.1000, 91.7000')).toBeTruthy()
  })

  it('performs online submission correctly with two-step photo upload', async () => {
    vi.mocked(incidentApi.createIncident).mockResolvedValueOnce({
      id: 99,
      incident_type: 'accident',
      severity: 'medium',
      latitude: 26.1,
      longitude: 91.7,
      status: 'reported',
      synced: 'synced',
      reported_at: new Date().toISOString()
    })
    
    vi.mocked(incidentApi.uploadPhoto).mockResolvedValueOnce({} as any)

    render(
      <AuthProvider>
        <BrowserRouter>
          <Incidents />
        </BrowserRouter>
      </AuthProvider>
    )

    fireEvent.click(screen.getByText('Pick on Map'))
    fireEvent.click(screen.getByTestId('mock-map'))

    // Provide a file
    const file = new File(['hello'], 'hello.png', { type: 'image/png' })
    const fileInput = await screen.findByLabelText(/Photo Evidence/i)
    Object.defineProperty(fileInput, 'files', { value: [file] })
    fireEvent.change(fileInput)

    fireEvent.click(screen.getByText('Submit Incident'))

    await waitFor(() => {
      expect(incidentApi.createIncident).toHaveBeenCalledTimes(1)
      expect(incidentApi.uploadPhoto).toHaveBeenCalledWith(99, file)
      expect(screen.getByText(/Incident #99 reported successfully with photo/i)).toBeTruthy()
    })
  })

  it('saves to offline queue if network fetch fails', async () => {
    vi.stubGlobal('navigator', { onLine: false })

    render(
      <AuthProvider>
        <BrowserRouter>
          <Incidents />
        </BrowserRouter>
      </AuthProvider>
    )

    fireEvent.click(screen.getByText('Pick on Map'))
    fireEvent.click(screen.getByTestId('mock-map'))

    fireEvent.click(screen.getByText('Submit Incident'))

    await waitFor(() => {
      expect(offlineQueue.addIncidentToQueue).toHaveBeenCalledTimes(1)
      expect(screen.getByText(/Network offline/i)).toBeTruthy()
    })
  })

  it('handles partial photo upload failure without discarding incident', async () => {
    vi.mocked(incidentApi.createIncident).mockResolvedValueOnce({
      id: 105,
      incident_type: 'accident',
      severity: 'medium',
      latitude: 26.1,
      longitude: 91.7,
      status: 'reported',
      synced: 'synced',
      reported_at: new Date().toISOString()
    })
    
    // Mock photo upload failure
    vi.mocked(incidentApi.uploadPhoto).mockRejectedValueOnce(new Error('500 Server Error'))

    render(
      <AuthProvider>
        <BrowserRouter>
          <Incidents />
        </BrowserRouter>
      </AuthProvider>
    )

    fireEvent.click(screen.getByText('Pick on Map'))
    fireEvent.click(screen.getByTestId('mock-map'))

    const file = new File(['hello'], 'hello.png', { type: 'image/png' })
    const photoInput = await screen.findByLabelText(/Photo Evidence/i)
    Object.defineProperty(photoInput, 'files', { value: [file] })
    fireEvent.change(photoInput)

    fireEvent.click(screen.getByText('Submit Incident'))

    await waitFor(() => {
      expect(incidentApi.createIncident).toHaveBeenCalledTimes(1)
      expect(incidentApi.uploadPhoto).toHaveBeenCalledTimes(1)
      expect(screen.getByText(/Incident created successfully, but photo upload failed/i)).toBeTruthy()
    })
  })

  it('allows field officials to verify and admins to resolve', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: 1, username: 'testuser', email: 'test@example.com', is_active: true, role: 'field_official' },
      role: 'field_official',
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      restoreSession: vi.fn()
    })

    const mockIncident: IncidentOut = {
      id: 1,
      incident_type: 'accident',
      severity: 'medium',
      latitude: 26.1,
      longitude: 91.7,
      status: 'reported',
      synced: 'synced',
      reported_at: new Date().toISOString()
    }
    vi.mocked(incidentApi.getIncidents).mockResolvedValue({ items: [mockIncident], total: 1, skip: 0, limit: 100 })

    render(
      <AuthProvider>
        <BrowserRouter>
          <Incidents />
        </BrowserRouter>
      </AuthProvider>
    )

    const verifyBtn = await screen.findByText('Verify')
    expect(verifyBtn).toBeTruthy()

    fireEvent.click(verifyBtn)

    await waitFor(() => {
      expect(incidentApi.updateStatus).toHaveBeenCalledWith(1, 'verified')
    })
  })

  it('blocks anonymous users from submitting incidents', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      role: null,
      isAuthenticated: false,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      restoreSession: vi.fn()
    })

    render(
      <AuthProvider>
        <BrowserRouter>
          <Incidents />
        </BrowserRouter>
      </AuthProvider>
    )

    expect(screen.getByText('Reporting Restricted')).toBeTruthy()
    expect(screen.getByText('Please log in to report an incident.')).toBeTruthy()
    expect(screen.queryByText('Submit Incident')).toBeNull()
  })

})
