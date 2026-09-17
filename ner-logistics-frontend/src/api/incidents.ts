import { fetchJson } from './client'
import { components } from './generated/schema'

export type IncidentCreate = components['schemas']['IncidentCreate']
export type IncidentOut = components['schemas']['IncidentOut']
export type IncidentStatusUpdate = components['schemas']['IncidentStatusUpdate']
export type IncidentSyncBatchResponse = components['schemas']['IncidentSyncBatchResponse']
export type PaginatedIncidentOut = components['schemas']['PaginatedResponse_IncidentOut_']

export const incidentApi = {
  getIncidents: (
    params: {
      incident_type?: string
      severity?: string
      road_id?: number
      bridge_id?: number
      status?: string
      start_date?: string
      end_date?: string
      skip?: number
      limit?: number
    } = {}
  ) => {
    const query = new URLSearchParams()
    if (params.incident_type) query.append('incident_type', params.incident_type)
    if (params.severity) query.append('severity', params.severity)
    if (params.road_id) query.append('road_id', params.road_id.toString())
    if (params.bridge_id) query.append('bridge_id', params.bridge_id.toString())
    if (params.status) query.append('status', params.status)
    if (params.start_date) query.append('start_date', params.start_date)
    if (params.end_date) query.append('end_date', params.end_date)
    if (params.skip !== undefined) query.append('skip', params.skip.toString())
    if (params.limit !== undefined) query.append('limit', params.limit.toString())
    
    return fetchJson<PaginatedIncidentOut>(`/incidents/?${query.toString()}`)
  },

  createIncident: (data: IncidentCreate) =>
    fetchJson<IncidentOut>('/incidents/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }),

  updateStatus: (incidentId: number, status: string) =>
    fetchJson<IncidentOut>(`/incidents/${incidentId}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
    }),

  uploadPhoto: async (incidentId: number, photo: Blob | File) => {
    const formData = new FormData()
    formData.append('file', photo, photo instanceof File ? photo.name : 'photo.jpg')
    
    return fetchJson<IncidentOut>(`/incidents/${incidentId}/photo`, {
      method: 'POST',
      body: formData,
      // Pass a custom flag to bypass default content-type header logic in fetchJson if necessary
      // Actually fetchJson in this project automatically omits Content-Type if body is FormData
    })
  },

  syncBatch: (incidents: IncidentCreate[]) =>
    fetchJson<IncidentSyncBatchResponse>('/incidents/sync-batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(incidents)
    })
}
