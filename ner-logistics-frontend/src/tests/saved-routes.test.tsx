import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import { SavedRoutes } from '../pages/SavedRoutes'
import { routesApi } from '../api/routes'
import { infrastructureApi } from '../api/infrastructure'
import { useAuth } from '../contexts/AuthContext'

vi.mock('../api/routes', () => ({
  routesApi: {
    createRoute: vi.fn(),
    addRoadToRoute: vi.fn()
  }
}))

vi.mock('../api/infrastructure', () => ({
  infrastructureApi: {
    getRoads: vi.fn().mockResolvedValue({ items: [] }),
    getRoadsBbox: vi.fn(),
    getRegistry: async () => ({ states: [] })
  }
}))

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn()
}))

describe('Phase 5: Saved Routes', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAuth).mockReturnValue({ role: 'admin' } as any)
  })

  it('2. 403 authorization lock for non-admin', async () => {
    vi.mocked(useAuth).mockReturnValue({ role: 'field_official' } as any)
    
    render(<SavedRoutes />)
    
    expect(screen.getByText('Access Denied')).toBeInTheDocument()
    expect(screen.queryByText('Create New Route')).not.toBeInTheDocument()
  })

  it('1. basic UI renders for admin', async () => {
    render(<SavedRoutes />)
    
    expect(screen.getByText('Saved Routes')).toBeInTheDocument()
    expect(screen.getByText('1. Create New Route')).toBeInTheDocument()
    expect(screen.getByText('2. Assign Road Sequence')).toBeInTheDocument()
  })

  it('3-4. POST /routes/ creates route', async () => {
    vi.mocked(routesApi.createRoute).mockResolvedValueOnce({ id: 10, name: 'Test Route', created_at: '' })
    
    render(<SavedRoutes />)

    const input = screen.getByPlaceholderText('e.g. Guwahati Supply Line A')
    fireEvent.change(input, { target: { value: 'Test Route' } })
    
    fireEvent.click(screen.getByText('Create Route'))

    await waitFor(() => {
      expect(routesApi.createRoute).toHaveBeenCalledWith({ name: 'Test Route' })
      expect(screen.getByText(/Route created successfully/i)).toBeInTheDocument()
    })
  })

  it('5-6. POST /routes/{id}/roads assigns road sequence', async () => {
    vi.mocked(infrastructureApi.getRoads).mockResolvedValueOnce({ 
      items: [{ id: 5, name: 'Road 5', district: 'Assam', start_lat: 0, start_lon: 0, end_lat: 0, end_lon: 0, length_km: 10 }] as any,
      total: 1, skip: 0, limit: 100
    })
    
    // Setup state by mocking create first
    vi.mocked(routesApi.createRoute).mockResolvedValueOnce({ id: 10, name: 'Test Route', created_at: '' })
    vi.mocked(routesApi.addRoadToRoute).mockResolvedValueOnce({ id: 1, route_id: 10, road_id: 5, sequence: 1 })
    
    render(<SavedRoutes />)

    // Wait for roads to load
    await waitFor(() => {
      expect(screen.getByText('Road 5 (ID: 5, Assam)')).toBeInTheDocument()
    })

    // Create route first
    fireEvent.change(screen.getByPlaceholderText('e.g. Guwahati Supply Line A'), { target: { value: 'Test' } })
    fireEvent.click(screen.getByText('Create Route'))
    
    await waitFor(() => expect(screen.getByText(/Route created successfully/i)).toBeInTheDocument())

    // Now assign road
    const select = screen.getByRole('combobox')
    fireEvent.change(select, { target: { value: '5' } })
    
    const seqInput = screen.getAllByRole('spinbutton').find(el => el.getAttribute('min') === '1')!
    fireEvent.change(seqInput, { target: { value: '1' } })

    fireEvent.click(screen.getByText('Add Road to Route'))

    await waitFor(() => {
      expect(routesApi.addRoadToRoute).toHaveBeenCalledWith(10, { road_id: 5, sequence: 1 })
      expect(screen.getByText('Current Sequence:')).toBeInTheDocument()
      expect(screen.getByText('Road 5')).toBeInTheDocument()
    })
  })
})
