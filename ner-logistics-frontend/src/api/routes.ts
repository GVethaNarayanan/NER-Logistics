import { fetchJson } from './client'
import { components } from './generated/schema'

export type RouteCreate = components['schemas']['RouteCreate']
export type RouteOut = components['schemas']['RouteOut']
export type RouteRoadCreate = components['schemas']['RouteRoadCreate']
export type RouteRoadOut = components['schemas']['RouteRoadOut']

// GET /routes/ doesn't exist in requirements, only POST /routes/ and POST /routes/{route_id}/roads
export const routesApi = {
  createRoute: (data: RouteCreate) =>
    fetchJson<RouteOut>('/routes/', {
      method: 'POST',
      body: JSON.stringify(data)
    }),
    
  addRoadToRoute: (routeId: number, data: RouteRoadCreate) =>
    fetchJson<RouteRoadOut>(`/routes/${routeId}/roads`, {
      method: 'POST',
      body: JSON.stringify(data)
    })
}
