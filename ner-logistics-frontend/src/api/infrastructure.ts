import { fetchJson } from './client'
import { PaginatedData, normalizePagination, fetchAllPaginated } from './pagination'
import type { components } from './generated/schema'

export type RoadOut = components['schemas']['RoadOut']
export type BridgeOut = components['schemas']['BridgeOut']
export type DistrictConnectivity = components['schemas']['DistrictConnectivity']

export interface DistrictBase {
  id: number;
  name: string;
  state_id: number;
  centroid_lat: number | null;
  centroid_lon: number | null;
}

export interface StateBase {
  id: number;
  name: string;
  districts: DistrictBase[];
}

export interface RegistryResponse {
  states: StateBase[];
}

export interface GeoJSONFeature {
  type: "Feature";
  geometry: any;
  properties: any;
}

export interface RoadGeoJSONCollection {
  type: "FeatureCollection";
  features: GeoJSONFeature[];
  total_matched: number;
}

export const infrastructureApi = {
  async getRoadsPage(skip = 0, limit = 100, districtId?: number): Promise<PaginatedData<RoadOut>> {
    const url = new URL('/roads/', window.location.origin)
    url.searchParams.append('skip', skip.toString())
    url.searchParams.append('limit', limit.toString())
    if (districtId) {
      url.searchParams.append('district_id', districtId.toString())
    }
    
    const res = await fetchJson<any>(url.pathname + url.search)
    return normalizePagination<RoadOut>(res)
  },

  async getRoads(districtId?: number): Promise<PaginatedData<RoadOut>> {
    return fetchAllPaginated((skip, limit) => this.getRoadsPage(skip, limit, districtId), 100)
  },

  async getRoadsBbox(params: {
    minLon: number, minLat: number,
    maxLon: number, maxLat: number,
    zoom: number,
    districtId?: number | string | null,
    limit?: number
  }): Promise<RoadGeoJSONCollection> {
    const url = new URL('/roads/bbox', window.location.origin)
    url.searchParams.append('min_lon', params.minLon.toString())
    url.searchParams.append('min_lat', params.minLat.toString())
    url.searchParams.append('max_lon', params.maxLon.toString())
    url.searchParams.append('max_lat', params.maxLat.toString())
    url.searchParams.append('zoom', params.zoom.toString())
    
    if (params.districtId !== undefined && params.districtId !== null) {
        if (params.districtId === 'unassigned') {
            url.searchParams.append('district_id', '-1')
        } else {
            url.searchParams.append('district_id', params.districtId.toString())
        }
    }
    if (params.limit) url.searchParams.append('limit', params.limit.toString())
    return fetchJson<RoadGeoJSONCollection>(url.pathname + url.search)
  },

  async getBridgesPage(skip = 0, limit = 100): Promise<PaginatedData<BridgeOut>> {
    const url = new URL('/bridges/', window.location.origin)
    url.searchParams.append('skip', skip.toString())
    url.searchParams.append('limit', limit.toString())
    
    const res = await fetchJson<any>(url.pathname + url.search)
    return normalizePagination<BridgeOut>(res)
  },

  async getBridges(limit = 100): Promise<PaginatedData<BridgeOut>> {
    return this.getBridgesPage(0, limit)
  },

  async getDistrictConnectivity(districtId: number): Promise<DistrictConnectivity> {
    return fetchJson<DistrictConnectivity>(`/districts/${districtId}/connectivity`)
  },

  async getDistrictBoundary(districtId: number): Promise<GeoJSONFeature> {
    return fetchJson<GeoJSONFeature>(`/districts/${districtId}/boundary`)
  },

  async locateDistrict(lat: number, lon: number): Promise<{ district_id: number | null, district_name: string | null }> {
    return fetchJson<{ district_id: number | null, district_name: string | null }>(`/districts/locate?lat=${lat}&lon=${lon}`)
  },

  async getRegistry(): Promise<RegistryResponse> {
    return fetchJson<RegistryResponse>('/districts/registry')
  }
}
