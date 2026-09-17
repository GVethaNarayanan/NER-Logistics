import { fetchJson } from './client'
import { components } from './generated/schema'

export type AlertOut = components['schemas']['AlertOut']
export type AlertCreate = components['schemas']['AlertCreate']
export type PaginatedAlertOut = components['schemas']['PaginatedResponse_AlertOut_']

export const alertApi = {
  getAlerts: (
    params: {
      alert_type?: string
      severity?: string
      status?: string
      skip?: number
      limit?: number
    } = {}
  ) => {
    const query = new URLSearchParams()
    if (params.alert_type) query.append('alert_type', params.alert_type)
    if (params.severity) query.append('severity', params.severity)
    if (params.status) query.append('status', params.status)
    if (params.skip !== undefined) query.append('skip', params.skip.toString())
    if (params.limit !== undefined) query.append('limit', params.limit.toString())
    
    return fetchJson<PaginatedAlertOut>(`/alerts/?${query.toString()}`)
  },

  createAlert: (data: AlertCreate) =>
    fetchJson<AlertOut>('/alerts/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    })
}
