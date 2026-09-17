import { getQueuedIncidents, updateQueuedIncident, removeQueuedIncident } from './offlineQueue'
import { incidentApi, IncidentCreate } from '../api/incidents'

let isSyncing = false
export function __resetSyncState() { isSyncing = false }

export async function syncOfflineIncidents(): Promise<{
  attempted: number
  succeeded: number
  failed: number
}> {
  if (isSyncing) {
    return { attempted: 0, succeeded: 0, failed: 0 }
  }

  // Quick check if browser thinks we are offline
  if (!navigator.onLine) {
    return { attempted: 0, succeeded: 0, failed: 0 }
  }

  isSyncing = true
  let attempted = 0
  let succeeded = 0
  let failed = 0

  try {
    const queue = await getQueuedIncidents()
    const pending = queue.filter(q => q.status === 'pending' || q.status === 'failed')

    if (pending.length === 0) {
      return { attempted: 0, succeeded: 0, failed: 0 }
    }

    attempted = pending.length
    
    // Mark all as syncing
    for (const item of pending) {
      item.status = 'syncing'
      await updateQueuedIncident(item)
    }

    const fullPayloadItems = pending.filter(p => p.payload !== null)
    const payloads = fullPayloadItems.map(item => item.payload as IncidentCreate)
    
    // 1. Sync batch of incidents for items that don't have a serverId yet
    let syncResult
    if (payloads.length > 0) {
      try {
        syncResult = await incidentApi.syncBatch(payloads)
      } catch (err: any) {
        // Network failed or 500 error during batch
        for (const item of fullPayloadItems) {
          item.status = 'failed'
          item.retryCount += 1
          item.lastError = err.message || 'Network error during sync'
          await updateQueuedIncident(item)
        }
        // Don't return yet, we might have items with serverId (photo only retries)
      }
    }

    // 2. Reconcile results for the batched items
    const successful_ids = syncResult?.successful_ids || []
    const failed_indexes = syncResult?.failed_indexes || []

    let successCursor = 0
    const failureMap = new Map<number, string>()
    failed_indexes.forEach((f: any) => failureMap.set(f.index, f.error))

    // We process all pending items
    let payloadIndex = 0
    for (let i = 0; i < pending.length; i++) {
      const item = pending[i]
      
      let serverId = item.serverId

      // If it doesn't have a serverId, it was part of the batch
      if (!serverId) {
        if (failureMap.has(payloadIndex)) {
          item.status = 'failed'
          item.retryCount += 1
          item.lastError = failureMap.get(payloadIndex)
          await updateQueuedIncident(item)
          failed += 1
          payloadIndex++
          continue
        } else if (successCursor < successful_ids.length) {
          serverId = successful_ids[successCursor]
          item.serverId = serverId
          successCursor++
        } else {
          // Sync failed for this batch entirely (handled above), or mismatch
          failed += 1
          payloadIndex++
          continue
        }
        payloadIndex++
      }

      // At this point we have a serverId (either just created or from a previous partial success)
      let photoSuccess = true
      if (item.photo) {
        try {
          await incidentApi.uploadPhoto(serverId, item.photo)
        } catch (photoErr: any) {
          photoSuccess = false
          item.status = 'failed'
          item.lastError = `Photo upload failed: ${photoErr.message}`
          item.retryCount += 1
          // DO NOT resubmit the incident, preserve local photo and server incident ID
          item.payload = null // Clear payload so we don't recreate it next time
          item.serverId = serverId
          await updateQueuedIncident(item)
        }
      }

      if (photoSuccess) {
        await removeQueuedIncident(item.localId)
        succeeded += 1
      } else {
        failed += 1
      }
    }

  } finally {
    isSyncing = false
  }

  return { attempted, succeeded, failed }
}
