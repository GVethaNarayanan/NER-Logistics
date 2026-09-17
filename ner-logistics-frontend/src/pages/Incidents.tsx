import React, { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { incidentApi, IncidentOut, IncidentCreate } from '../api/incidents'
import { infrastructureApi, RoadOut, BridgeOut } from '../api/infrastructure'
import { addIncidentToQueue, getQueuedIncidents, QueuedIncident } from '../lib/offlineQueue'
import { syncOfflineIncidents } from '../lib/syncService'
import { MapComponent } from '../components/dashboard/MapComponent'
import { AlertCircle, FileText, MapPin, Upload, RefreshCw, CheckCircle, Clock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { LoadingState } from '../components/shared/LoadingState'
import { ErrorState } from '../components/shared/ErrorState'
import { EmptyState } from '../components/shared/EmptyState'

export const Incidents: React.FC = () => {
  const { role, user } = useAuth()
  const { t } = useTranslation()
  const isFieldOfficialOrAdmin = role === 'admin' || role === 'field_official'

  const [incidents, setIncidents] = useState<IncidentOut[]>([])
  const [incidentsLoading, setIncidentsLoading] = useState(true)
  const [incidentsError, setIncidentsError] = useState<string | null>(null)

  const [roads, setRoads] = useState<RoadOut[]>([])
  const [bridges, setBridges] = useState<BridgeOut[]>([])

  // Queue state
  const [queue, setQueue] = useState<QueuedIncident[]>([])
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState<string | null>(null)

  // Form state
  const [formType, setFormType] = useState('accident')
  const [formDescription, setFormDescription] = useState('')
  const [formSeverity, setFormSeverity] = useState('medium')
  const [formLat, setFormLat] = useState<number | null>(null)
  const [formLon, setFormLon] = useState<number | null>(null)
  const [formRoadId, setFormRoadId] = useState<string>('')
  const [formBridgeId, setFormBridgeId] = useState<string>('')
  
  const [photo, setPhoto] = useState<File | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null)

  // Map state for tagging
  const [isPickingLocation, setIsPickingLocation] = useState(false)

  // Pagination / Filter
  const [skip] = useState(0)

  const loadIncidents = useCallback(async () => {
    setIncidentsLoading(true)
    try {
      const res = await incidentApi.getIncidents({ skip, limit: 20 })
      setIncidents(res.items)
      setIncidentsError(null)
    } catch (err: any) {
      setIncidentsError(err.message || 'Failed to load incidents')
    } finally {
      setIncidentsLoading(false)
    }
  }, [skip])

  const refreshQueue = useCallback(async () => {
    const q = await getQueuedIncidents()
    setQueue(q)
  }, [])

  useEffect(() => {
    loadIncidents()
    refreshQueue()
    infrastructureApi.getRoads().then(r => setRoads(r.items)).catch(console.error)
    infrastructureApi.getBridges().then(r => setBridges(r.items)).catch(console.error)
  }, [loadIncidents, refreshQueue])

  // Automatic sync on online
  useEffect(() => {
    const handleOnline = async () => {
      setSyncResult('Network restored. Attempting sync...')
      setSyncing(true)
      const res = await syncOfflineIncidents()
      setSyncing(false)
      if (res.attempted > 0) {
        setSyncResult(`Synced ${res.succeeded}, Failed ${res.failed}`)
      } else {
        setSyncResult(null)
      }
      refreshQueue()
      loadIncidents()
    }
    window.addEventListener('online', handleOnline)
    return () => window.removeEventListener('online', handleOnline)
  }, [refreshQueue, loadIncidents])

  const handleManualSync = async () => {
    setSyncResult('Syncing...')
    setSyncing(true)
    const res = await syncOfflineIncidents()
    setSyncing(false)
    setSyncResult(`Synced ${res.succeeded}, Failed ${res.failed}`)
    refreshQueue()
    loadIncidents()
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!user) {
      setSubmitError('You must be logged in to report an incident.')
      return
    }

    if (!isFieldOfficialOrAdmin) {
      setSubmitError('You do not have permission to report incidents.')
      return
    }

    if (formLat === null || formLon === null) {
      setSubmitError('Please select a location on the map')
      return
    }

    setSubmitting(true)
    setSubmitError(null)
    setSubmitSuccess(null)

    const payload: IncidentCreate = {
      incident_type: formType,
      description: formDescription || null,
      severity: formSeverity,
      latitude: formLat,
      longitude: formLon,
      road_id: formRoadId ? parseInt(formRoadId) : null,
      bridge_id: formBridgeId ? parseInt(formBridgeId) : null,
      reported_by: user.username
    }

    try {
      if (!navigator.onLine) {
        throw new Error('Network is offline')
      }

      // Online submission
      const created = await incidentApi.createIncident(payload)
      
      // Step 2: photo
      if (photo) {
        try {
          await incidentApi.uploadPhoto(created.id, photo)
          setSubmitSuccess(`Incident #${created.id} reported successfully with photo.`)
        } catch (photoErr: any) {
          setSubmitError(`Incident created successfully, but photo upload failed: ${photoErr.message}`)
        }
      } else {
        setSubmitSuccess(`Incident #${created.id} reported successfully.`)
      }

      // Reset form
      setFormDescription('')
      setFormLat(null)
      setFormLon(null)
      setFormRoadId('')
      setFormBridgeId('')
      setPhoto(null)
      loadIncidents()

    } catch (err: any) {
      // If network error (fetch fails), queue it
      if (err.message.includes('Failed to fetch') || err.message === 'Network is offline' || err.message.includes('NetworkError')) {
        try {
          await addIncidentToQueue(payload, photo)
          setSubmitSuccess('Network offline. Incident saved to local queue.')
          refreshQueue()
          setFormDescription('')
          setFormLat(null)
          setFormLon(null)
          setPhoto(null)
        } catch (queueErr) {
          setSubmitError('Failed to save incident offline.')
        }
      } else {
        // Server validation error (422) or other errors should NOT be queued
        setSubmitError(err.message || 'Submission failed')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const handleStatusUpdate = async (incidentId: number, targetStatus: string) => {
    try {
      await incidentApi.updateStatus(incidentId, targetStatus)
      loadIncidents()
    } catch (err: any) {
      alert(`Failed to update status: ${err.message}`)
    }
  }

  return (
    <div className="container mx-auto p-4 md:p-8 flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-3">
          <FileText className="w-8 h-8 text-primary" />
          {t('navigation.incidents', 'Field Incidents')}
        </h1>
        <p className="text-muted-foreground mt-2">{t('incidents.subtitle', 'Report and manage infrastructure incidents.')}</p>
      </div>

      {queue.length > 0 && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-amber-700 flex items-center gap-2">
              <Clock className="w-5 h-5" />
              {t('incidents.offline_queue', 'Offline Queue')} ({queue.length} items)
            </h3>
            <button
              onClick={handleManualSync}
              disabled={syncing}
              className="bg-amber-100 text-amber-800 hover:bg-amber-200 px-3 py-1.5 rounded text-sm font-medium flex items-center gap-2 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
              {syncing ? 'Syncing...' : 'Sync Now'}
            </button>
          </div>
          {syncResult && <p className="text-sm font-medium text-amber-700">{syncResult}</p>}
          
          <ul className="flex flex-col gap-2 mt-2">
            {queue.map(q => (
              <li key={q.localId} className="text-sm bg-background/50 border rounded p-2 flex justify-between items-center">
                <div className="flex flex-col">
                  <span className="font-medium">{q.payload?.incident_type || 'Photo Retry'}</span>
                  <span className="text-xs text-muted-foreground">Status: {q.status} {q.serverId ? `(Server ID: ${q.serverId})` : ''}</span>
                  {q.lastError && <span className="text-xs text-destructive font-medium mt-1">Error: {q.lastError}</span>}
                </div>
                {q.photo && <span className="text-xs px-2 py-1 bg-blue-100 text-blue-800 rounded">Photo attached</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        
        {/* Report Form */}
        {isFieldOfficialOrAdmin ? (
          <div className="bg-card border rounded-lg p-6 shadow-sm flex flex-col gap-4">
          <h2 className="font-semibold text-lg border-b pb-2">{t('incidents.report_new', 'Report New Incident')}</h2>
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium">{t('incidents.type', 'Type')}</label>
                <select value={formType} onChange={e => setFormType(e.target.value)} className="bg-background border rounded p-2 text-sm" required>
                  <option value="accident">Accident</option>
                  <option value="landslide">Landslide</option>
                  <option value="flood">Flood</option>
                  <option value="bridge_damage">Bridge Damage</option>
                  <option value="roadblock">Roadblock</option>
                </select>
              </div>
              
              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium">{t('incidents.severity', 'Severity')}</label>
                <select value={formSeverity} onChange={e => setFormSeverity(e.target.value)} className="bg-background border rounded p-2 text-sm" required>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium">{t('incidents.location', 'Location (Geo-tag)')}</label>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setIsPickingLocation(!isPickingLocation)}
                  className={`flex-1 py-2 rounded text-sm font-medium border flex items-center justify-center gap-2 transition-colors ${
                    isPickingLocation ? 'bg-primary text-primary-foreground border-primary' : 'bg-muted hover:bg-muted/80 border-input'
                  }`}
                >
                  <MapPin className="w-4 h-4" />
                  {isPickingLocation ? t('incidents.click_map', 'Click Map to Pick...') : t('incidents.pick_map', 'Pick on Map')}
                </button>
                <div className="flex-1 bg-background border rounded p-2 text-sm text-center font-mono text-muted-foreground">
                  {formLat && formLon ? `${formLat.toFixed(4)}, ${formLon.toFixed(4)}` : t('incidents.no_location', 'No location selected')}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium">{t('incidents.assoc_road', 'Associated Road (Optional)')}</label>
                <select value={formRoadId} onChange={e => setFormRoadId(e.target.value)} className="bg-background border rounded p-2 text-sm">
                  <option value="">-- {t('incidents.none', 'None')} --</option>
                  {roads.map(r => <option key={r.id} value={r.id}>{r.name} (ID: {r.id})</option>)}
                </select>
              </div>
              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium">{t('incidents.assoc_bridge', 'Associated Bridge (Optional)')}</label>
                <select value={formBridgeId} onChange={e => setFormBridgeId(e.target.value)} className="bg-background border rounded p-2 text-sm">
                  <option value="">-- {t('incidents.none', 'None')} --</option>
                  {bridges.map(b => <option key={b.id} value={b.id}>{b.name} (ID: {b.id})</option>)}
                </select>
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <label className="text-sm font-medium">{t('incidents.description', 'Description')}</label>
              <textarea 
                value={formDescription} 
                onChange={e => setFormDescription(e.target.value)} 
                className="bg-background border rounded p-2 text-sm min-h-[80px]"
                placeholder={t('incidents.desc_placeholder', 'Provide incident details...')}
              />
            </div>

            <div className="flex flex-col gap-2">
              <label htmlFor="photo-upload" className="text-sm font-medium">{t('incidents.photo', 'Photo Evidence (Optional)')}</label>
              <input 
                id="photo-upload"
                type="file" 
                accept="image/*"
                onChange={e => setPhoto(e.target.files ? e.target.files[0] : null)}
                className="text-sm text-muted-foreground file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-primary/10 file:text-primary hover:file:bg-primary/20"
              />
            </div>

            <button
              type="submit"
              disabled={submitting || !formLat || !formLon}
              className="mt-2 bg-primary text-primary-foreground py-2 rounded font-medium flex items-center justify-center gap-2 hover:bg-primary/90 disabled:opacity-50"
            >
              <Upload className="w-4 h-4" />
              {submitting ? t('incidents.submitting', 'Submitting...') : t('incidents.submit', 'Submit Incident')}
            </button>

            {submitError && (
              <div className="mt-2">
                <ErrorState error={submitError} />
              </div>
            )}

            {submitSuccess && (
              <div className="p-3 bg-emerald-500/10 text-emerald-600 border border-emerald-500/20 rounded text-sm flex gap-2 items-start mt-2">
                <CheckCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{submitSuccess}</span>
              </div>
            )}

          </form>
        </div>
        ) : (
          <div className="bg-card border rounded-lg p-6 shadow-sm flex flex-col gap-4 items-center justify-center text-center">
            <AlertCircle className="w-12 h-12 text-muted-foreground mb-2" />
            <h2 className="font-semibold text-lg">{t('incidents.restricted_title', 'Reporting Restricted')}</h2>
            <p className="text-muted-foreground text-sm">
              {!user 
                ? t('incidents.restricted_login', 'Please log in to report an incident.') 
                : t('incidents.restricted_perms', 'You do not have permission to report incidents. Only field officials and administrators can submit reports.')}
            </p>
          </div>
        )}

        {/* Map geo tagger */}
        <div className="bg-card rounded-lg shadow-sm border overflow-hidden min-h-[500px] h-full flex flex-col relative">
           {isPickingLocation && (
             <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[1000] bg-primary text-primary-foreground px-4 py-2 rounded-full font-bold shadow-lg pointer-events-none">
               {t('incidents.click_anywhere', 'Click anywhere on the map to drop a pin')}
             </div>
           )}
           <MapComponent 
             roads={roads}
             bridges={bridges}
             onDistrictSelect={() => {}}
             onMapClick={(lat, lng) => {
               if (isPickingLocation) {
                 setFormLat(lat)
                 setFormLon(lng)
                 setIsPickingLocation(false)
               }
             }}
             origin={formLat && formLon ? [formLat, formLon] : null}
           />
        </div>

      </div>

      {/* Incident List */}
      <div className="bg-card border rounded-lg p-6 shadow-sm flex flex-col gap-4">
        <div className="flex items-center justify-between border-b pb-2">
          <h2 className="font-semibold text-lg">Reported Incidents</h2>
          <button onClick={loadIncidents} className="text-sm font-medium text-blue-500 hover:underline">Refresh</button>
        </div>

        {incidentsLoading && <LoadingState message={t('loading.default', 'Loading...')} />}
        {incidentsError && <ErrorState error={incidentsError} onRetry={loadIncidents} />}
        
        {!incidentsLoading && !incidentsError && incidents.length === 0 && (
          <EmptyState 
            title={t('incidents.no_incidents', 'No Incidents Reported')} 
            description={t('incidents.no_incidents_desc', 'There are no reported incidents at this time.')} 
          />
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {incidents.map(inc => (
            <div key={inc.id} className="border rounded-lg p-4 flex flex-col gap-3">
              <div className="flex justify-between items-start">
                <div>
                  <h3 className="font-bold uppercase text-sm">{inc.incident_type}</h3>
                  <span className="text-xs text-muted-foreground">ID: {inc.id} • {new Date(inc.reported_at).toLocaleString()}</span>
                </div>
                <div className="flex gap-2">
                  <span className={`text-xs px-2 py-1 rounded font-bold uppercase ${
                    inc.severity === 'high' ? 'bg-red-500 text-white' : 
                    inc.severity === 'medium' ? 'bg-amber-500 text-white' : 'bg-emerald-500 text-white'
                  }`}>{inc.severity}</span>
                  <span className={`text-xs px-2 py-1 rounded font-bold uppercase border ${
                    inc.status === 'reported' ? 'border-amber-500 text-amber-500' :
                    inc.status === 'verified' ? 'border-blue-500 text-blue-500' : 'border-emerald-500 text-emerald-500'
                  }`}>{inc.status}</span>
                </div>
              </div>
              
              {inc.description && <p className="text-sm text-muted-foreground bg-muted/50 p-2 rounded">{inc.description}</p>}
              
              {inc.photo_url && (
                <div className="w-full h-32 rounded bg-muted flex items-center justify-center overflow-hidden border">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={`http://127.0.0.1:8000${inc.photo_url}`} alt="Incident evidence" className="object-cover w-full h-full" />
                </div>
              )}

              <div className="flex justify-between items-center mt-2 border-t pt-2">
                <span className="text-xs text-muted-foreground font-mono">
                  {inc.latitude.toFixed(4)}, {inc.longitude.toFixed(4)}
                </span>
                
                {isFieldOfficialOrAdmin && (
                  <div className="flex gap-2">
                    {inc.status === 'reported' && (
                      <button 
                        onClick={() => handleStatusUpdate(inc.id, 'verified')}
                        className="text-xs bg-blue-100 text-blue-700 px-3 py-1 rounded font-medium hover:bg-blue-200"
                      >
                        Verify
                      </button>
                    )}
                    {inc.status === 'verified' && (
                      <button 
                        onClick={() => handleStatusUpdate(inc.id, 'resolved')}
                        className="text-xs bg-emerald-100 text-emerald-700 px-3 py-1 rounded font-medium hover:bg-emerald-200"
                      >
                        Resolve
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
