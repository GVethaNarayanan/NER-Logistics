import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import '@testing-library/jest-dom'
import { Vehicles } from '../pages/Vehicles'
import { vehicleApi } from '../api/vehicles'
import { useAuth } from '../contexts/AuthContext'

vi.mock('../api/vehicles', () => ({
  vehicleApi: {
    getVehicles: vi.fn(),
    getVehicleHistory: vi.fn(),
    assignRoute: vi.fn()
  }
}))

vi.mock('../api/infrastructure', () => ({
  infrastructureApi: {
    getRoads: vi.fn().mockResolvedValue({ items: [] }),
    getRoadsBbox: vi.fn().mockResolvedValue({ items: [] }),
    getRegistry: vi.fn().mockResolvedValue({ states: [] }),
    getBridges: vi.fn().mockResolvedValue({ items: [] })
  }
}))

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn()
}))

vi.mock('../components/dashboard/MapComponent', () => ({
  MapComponent: ({ vehicles, vehicleHistory }: any) => (
    <div data-testid="map-component">
      Map
      <div data-testid="vehicle-count">{vehicles?.length || 0}</div>
      <div data-testid="history-count">{vehicleHistory?.length || 0}</div>
    </div>
  )
}))

describe('Phase 5: Vehicles & Tracking', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAuth).mockReturnValue({ role: 'admin' } as any)
    vi.mocked(vehicleApi.getVehicles).mockResolvedValue({ items: [], total: 0, skip: 0, limit: 100 })
    vi.mocked(vehicleApi.getVehicleHistory).mockResolvedValue({ items: [], total: 0, skip: 0, limit: 100 })
  })

  const dummyVehicle = {
    id: 1,
    vehicle_number: 'TEST-123',
    status: 'in_transit',
    current_lat: 26.1,
    current_lon: 92.1,
    speed_kmh: 45.2,
    destination: 'Guwahati',
    current_route_id: 10,
    current_route_progress_km: 12.5,
    updated_at: new Date().toISOString()
  }

  it('8. vehicle list renders', async () => {
    vi.mocked(vehicleApi.getVehicles).mockResolvedValueOnce({ items: [dummyVehicle], total: 1, skip: 0, limit: 100 })
    render(<Vehicles />)

    await waitFor(() => {
      expect(screen.getByText('TEST-123')).toBeInTheDocument()
      expect(screen.getByText('in_transit')).toBeInTheDocument()
      expect(screen.getByText('45 km/h')).toBeInTheDocument() // Rounded in list
    })
  })

  it('12. simulated badge displays', async () => {
    vi.mocked(vehicleApi.getVehicles).mockResolvedValueOnce({ items: [dummyVehicle], total: 1, skip: 0, limit: 100 })
    render(<Vehicles />)

    await waitFor(() => {
      expect(screen.getAllByText('SIMULATED GPS')[0]).toBeInTheDocument()
    })
  })

  it('16. vehicle detail renders current route/progress fields', async () => {
    vi.mocked(vehicleApi.getVehicles).mockResolvedValueOnce({ items: [dummyVehicle], total: 1, skip: 0, limit: 100 })
    render(<Vehicles />)

    await waitFor(() => {
      expect(screen.getByText('TEST-123')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('TEST-123').closest('button')!)

    await waitFor(() => {
      expect(screen.getByText('Vehicle Details: TEST-123')).toBeInTheDocument()
      expect(screen.getByText('45.2 km/h')).toBeInTheDocument() // Exact in detail
      expect(screen.getByText('10')).toBeInTheDocument() // Route ID
      expect(screen.getByText('12.5 km')).toBeInTheDocument() // Route progress
      expect(screen.getByText(/Vehicle location data is simulated by the backend/i)).toBeInTheDocument()
    })
  })

  it('17-19. history loads on select', async () => {
    vi.mocked(vehicleApi.getVehicles).mockResolvedValueOnce({ items: [dummyVehicle], total: 1, skip: 0, limit: 100 })
    vi.mocked(vehicleApi.getVehicleHistory).mockResolvedValueOnce({
      items: [{ id: 1, vehicle_id: 1, latitude: 26.1, longitude: 92.1, data_source: 'simulated', timestamp: '' }],
      total: 1, skip: 0, limit: 100
    })

    render(<Vehicles />)
    
    await waitFor(() => expect(screen.getByText('TEST-123')).toBeInTheDocument())
    
    // initially 0 history points
    expect(screen.getByTestId('history-count')).toHaveTextContent('0')

    // select vehicle
    fireEvent.click(screen.getByText('TEST-123').closest('button')!)

    await waitFor(() => {
      expect(vehicleApi.getVehicleHistory).toHaveBeenCalledWith(1)
      expect(screen.getByTestId('history-count')).toHaveTextContent('1')
    })
  })

  it('21-22. admin route assignment UI works for admin', async () => {
    vi.mocked(vehicleApi.getVehicles).mockResolvedValueOnce({ items: [dummyVehicle], total: 1, skip: 0, limit: 100 })
    
    render(<Vehicles />)
    await waitFor(() => expect(screen.getByText('TEST-123')).toBeInTheDocument())
    fireEvent.click(screen.getByText('TEST-123').closest('button')!)

    await waitFor(() => {
      expect(screen.getByText('ADMIN: ROUTE ASSIGNMENT')).toBeInTheDocument()
    })

    const input = screen.getByPlaceholderText('Route ID')
    fireEvent.change(input, { target: { value: '99' } })

    vi.mocked(vehicleApi.assignRoute).mockResolvedValueOnce({ ...dummyVehicle, current_route_id: 99 })
    
    fireEvent.click(screen.getByText('Assign'))

    await waitFor(() => {
      expect(vehicleApi.assignRoute).toHaveBeenCalledWith(1, 99)
      expect(screen.getByText('Route assigned successfully!')).toBeInTheDocument()
    })
  })

  it('22. unauthorized route assignment UI is hidden', async () => {
    vi.mocked(useAuth).mockReturnValue({ role: 'field_official' } as any)
    vi.mocked(vehicleApi.getVehicles).mockResolvedValueOnce({ items: [dummyVehicle], total: 1, skip: 0, limit: 100 })
    
    render(<Vehicles />)
    await waitFor(() => expect(screen.getByText('TEST-123')).toBeInTheDocument())
    fireEvent.click(screen.getByText('TEST-123').closest('button')!)

    await waitFor(() => {
      expect(screen.getByText('Vehicle Details: TEST-123')).toBeInTheDocument()
      expect(screen.queryByText('ADMIN: ROUTE ASSIGNMENT')).not.toBeInTheDocument()
    })
  })
})
