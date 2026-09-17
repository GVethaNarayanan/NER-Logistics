import { describe, it, expect } from 'vitest'
import { fetchJson } from './client'

describe('Real Backend Smoke Test', () => {
  it('successfully fetches health from the live backend', async () => {
    // This assumes the backend is running at VITE_API_BASE_URL
    const data = await fetchJson<{ status: string }>('/')
    expect(data).toHaveProperty('status', 'ok')
  })
})
