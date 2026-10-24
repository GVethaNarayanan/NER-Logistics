import { fetchJson } from './client'
import { components } from './generated/schema'

export type RouteCreate = components['schemas']['RouteCreate']
export type RouteOut = components['schemas']['RouteOut']
export type RouteRoadCreate = components['schemas']['RouteRoadCreate']
export type RouteRoadOut = components['schemas']['RouteRoadOut']

export interface SavedRouteItem {
  id: number
  name: string
  road_count: number
  total_distance_km: number
  created_at: string | null
}

export interface SavedRouteDetail {
  id: number
  name: string
  route_status: 'open' | 'restricted' | 'blocked'
  blocked_road_count: number
  restricted_road_count: number
  segments: Array<{
    id: number
    sequence: number
    road_id: number
    road_name: string | null
    road_type: string | null
    road_status: string | null
    road_length_km: number | null
    is_reversed: boolean
  }>
  total_distance_km: number
}

export const routesApi = {
  // Public — any user can view
  listRoutes: () =>
    fetchJson<{ items: SavedRouteItem[], total: number }>('/routes/'),

  getRouteDetail: (routeId: number) =>
    fetchJson<SavedRouteDetail>(`/routes/${routeId}`),

  // Admin only — create/modify/delete
  createRoute: (data: RouteCreate) =>
    fetchJson<RouteOut>('/routes/', {
      method: 'POST',
      body: JSON.stringify(data)
    }),
    
  addRoadToRoute: (routeId: number, data: RouteRoadCreate) =>
    fetchJson<RouteRoadOut>(`/routes/${routeId}/roads`, {
      method: 'POST',
      body: JSON.stringify(data)
    }),

  deleteRoute: (routeId: number) =>
    fetchJson<void>(`/routes/${routeId}`, { method: 'DELETE' }),
}
