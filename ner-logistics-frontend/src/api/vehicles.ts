import { fetchJson } from './client'
import { components } from './generated/schema'

export type VehicleOut = components['schemas']['VehicleOut']
export type PaginatedVehicleOut = components['schemas']['PaginatedResponse_VehicleOut_']
export type VehicleLocationHistoryOut = components['schemas']['VehicleLocationHistoryOut']
export type PaginatedVehicleLocationHistoryOut = components['schemas']['PaginatedResponse_VehicleLocationHistoryOut_']

export const vehicleApi = {
  getVehicles: (skip = 0, limit = 100) => 
    fetchJson<PaginatedVehicleOut>(`/vehicles/?skip=${skip}&limit=${limit}`),
    
  getVehicle: (vehicleId: number) =>
    fetchJson<VehicleOut>(`/vehicles/${vehicleId}`),
    
  getVehicleHistory: (vehicleId: number, skip = 0, limit = 100) =>
    fetchJson<PaginatedVehicleLocationHistoryOut>(`/vehicles/${vehicleId}/history?skip=${skip}&limit=${limit}`),
    
  assignRoute: (vehicleId: number, routeId: number) =>
    fetchJson<VehicleOut>(`/vehicles/${vehicleId}/route`, {
      method: 'PATCH',
      body: JSON.stringify({ route_id: routeId })
    })
}
