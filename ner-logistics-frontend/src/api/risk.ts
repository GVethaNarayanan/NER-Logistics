import { fetchJson } from './client'
import type { components } from './generated/schema'

export type RiskInput = components['schemas']['RiskInput']
export type RiskOutput = components['schemas']['RiskOutput']

export const riskApi = {
  predictRisk: async (data: RiskInput): Promise<RiskOutput> => {
    return fetchJson<RiskOutput>('/risk/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
  }
}
