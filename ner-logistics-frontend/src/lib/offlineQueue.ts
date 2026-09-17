import { IncidentCreate } from '../api/incidents'

export interface QueuedIncident {
  localId: string
  payload: IncidentCreate | null // Can be null if already synced but photo pending
  serverId?: number // Populated if incident synced but photo failed
  photo?: Blob | null
  createdAt: number
  retryCount: number
  status: 'pending' | 'syncing' | 'failed'
  lastError?: string
}

const DB_NAME = 'NerLogisticsOfflineDB'
const STORE_NAME = 'incidents_queue'
const DB_VERSION = 1

let dbPromise: Promise<IDBDatabase> | null = null

function getDB(): Promise<IDBDatabase> {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, DB_VERSION)

      request.onerror = () => reject(request.error)
      request.onsuccess = () => resolve(request.result)

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result
        if (!db.objectStoreNames.contains(STORE_NAME)) {
          db.createObjectStore(STORE_NAME, { keyPath: 'localId' })
        }
      }
    })
  }
  return dbPromise
}

export async function addIncidentToQueue(payload: IncidentCreate, photo?: Blob | null): Promise<QueuedIncident> {
  const db = await getDB()
  const localId = crypto.randomUUID()
  const record: QueuedIncident = {
    localId,
    payload,
    photo,
    createdAt: Date.now(),
    retryCount: 0,
    status: 'pending'
  }

  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    const request = store.add(record)

    request.onsuccess = () => resolve(record)
    request.onerror = () => reject(request.error)
  })
}

export async function getQueuedIncidents(): Promise<QueuedIncident[]> {
  const db = await getDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly')
    const store = tx.objectStore(STORE_NAME)
    const request = store.getAll()

    request.onsuccess = () => resolve(request.result.sort((a, b) => a.createdAt - b.createdAt))
    request.onerror = () => reject(request.error)
  })
}

export async function updateQueuedIncident(record: QueuedIncident): Promise<void> {
  const db = await getDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    const request = store.put(record)

    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error)
  })
}

export async function removeQueuedIncident(localId: string): Promise<void> {
  const db = await getDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    const request = store.delete(localId)

    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error)
  })
}
