import { fetchJson } from './client'
import type { components } from './generated/schema'

export type RouteRequest = components['schemas']['RouteRequest']
export type RouteResponse = components['schemas']['RouteResponse']

export const routingApi = {
  computeRoute: async (data: RouteRequest): Promise<RouteResponse> => {
    return fetchJson<RouteResponse>('/routing/route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
  }
}
