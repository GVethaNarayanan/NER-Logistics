import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as syncService from '../lib/syncService'
import * as offlineQueue from '../lib/offlineQueue'
import { incidentApi, IncidentCreate } from '../api/incidents'

// Mock offline queue with in-memory state
vi.mock('../lib/offlineQueue', () => {
  let queue: any[] = []
  return {
    addIncidentToQueue: vi.fn(async (payload, photo) => {
      const q = { localId: Math.random().toString(), payload, photo, status: 'pending', retryCount: 0 }
      queue.push(q)
      return q
    }),
    getQueuedIncidents: vi.fn(async () => queue),
    updateQueuedIncident: vi.fn(async (q) => {
      const idx = queue.findIndex(x => x.localId === q.localId)
      if (idx !== -1) queue[idx] = q
    }),
    removeQueuedIncident: vi.fn(async (id) => {
      queue = queue.filter(x => x.localId !== id)
    }),
    __resetQueue: () => { queue = [] }
  }
})

vi.mock('../api/incidents', () => ({
  incidentApi: {
    syncBatch: vi.fn(),
    uploadPhoto: vi.fn()
  }
}))

describe('Phase 6 Final Fixes: syncService Offline Photo Retry Safety & Mixed Batches', () => {
  beforeEach(() => {
    vi.stubGlobal('navigator', { onLine: true })
    syncService.__resetSyncState()
    ;(offlineQueue as any).__resetQueue()
    vi.clearAllMocks()
  })

  it('A. Mixed batch partial success', async () => {
    const validPayload: IncidentCreate = { incident_type: 'accident', severity: 'low', latitude: 1, longitude: 1 }
    const invalidPayload: IncidentCreate = { incident_type: 'flood', severity: 'high', latitude: 2, longitude: 2 }
    
    await offlineQueue.addIncidentToQueue(validPayload, null)
    const q2 = await offlineQueue.addIncidentToQueue(invalidPayload, null)

    vi.mocked(incidentApi.syncBatch).mockResolvedValueOnce({
      successful_ids: [100],
      failed_indexes: [{ index: 1, error: 'Invalid data' }]
    })

    const res = await syncService.syncOfflineIncidents()
    expect(res.attempted).toBe(2)
    expect(res.succeeded).toBe(1)
    expect(res.failed).toBe(1)

    const queue = await offlineQueue.getQueuedIncidents()
    expect(queue.length).toBe(1)
    
    const remaining = queue[0]
    expect(remaining.localId).toBe(q2.localId)
    expect(remaining.status).toBe('failed')
    expect(remaining.lastError).toBe('Invalid data')
  })

  it('B. Successful incident + failed photo & C. Duplicate protection', async () => {
    const payload: IncidentCreate = { incident_type: 'landslide', severity: 'high', latitude: 3, longitude: 3 }
    const photo = new File(['dummy'], 'photo.png', { type: 'image/png' })
    const q = await offlineQueue.addIncidentToQueue(payload, photo)

    vi.mocked(incidentApi.syncBatch).mockResolvedValueOnce({
      successful_ids: [999],
      failed_indexes: []
    })
    vi.mocked(incidentApi.uploadPhoto).mockRejectedValueOnce(new Error('Network drop during photo'))

    const res1 = await syncService.syncOfflineIncidents()
    expect(res1.attempted).toBe(1)
    expect(res1.succeeded).toBe(0)
    expect(res1.failed).toBe(1)

    const queueAfterFail = await offlineQueue.getQueuedIncidents()
    expect(queueAfterFail.length).toBe(1)
    
    const remaining = queueAfterFail[0]
    expect(remaining.localId).toBe(q.localId)
    expect(remaining.serverId).toBe(999)
    expect(remaining.payload).toBeNull()
    expect(remaining.photo).not.toBeNull()
    expect(remaining.lastError).toContain('Network drop')

    vi.mocked(incidentApi.syncBatch).mockClear()
    vi.mocked(incidentApi.uploadPhoto).mockResolvedValueOnce({} as any)

    const res2 = await syncService.syncOfflineIncidents()
    expect(res2.attempted).toBe(1)
    expect(res2.succeeded).toBe(1)
    expect(res2.failed).toBe(0)

    expect(incidentApi.syncBatch).not.toHaveBeenCalled()
    expect(incidentApi.uploadPhoto).toHaveBeenCalledWith(999, expect.any(Object))

    const finalQueue = await offlineQueue.getQueuedIncidents()
    expect(finalQueue.length).toBe(0)
  })
})
