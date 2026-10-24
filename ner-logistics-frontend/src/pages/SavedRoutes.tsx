import React, { useState, useEffect } from 'react'
import { infrastructureApi, RoadOut } from '../api/infrastructure'
import { routesApi, RouteOut, RouteRoadOut, SavedRouteItem, SavedRouteDetail } from '../api/routes'
import { AlertCircle, Route as RouteIcon, Plus, Check, ChevronRight, Shield, AlertTriangle, XCircle, MapPin } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useTranslation } from 'react-i18next'
import { ErrorState } from '../components/shared/ErrorState'

export const SavedRoutes: React.FC = () => {
  const { role } = useAuth()
  const isAdmin = role === 'admin'
  const { t } = useTranslation()

  // ── Saved routes list (visible to ALL users) ──
  const [savedRoutes, setSavedRoutes] = useState<SavedRouteItem[]>([])
  const [routesLoading, setRoutesLoading] = useState(true)
  const [selectedRoute, setSelectedRoute] = useState<SavedRouteDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // ── Admin-only create state ──
  const [roads, setRoads] = useState<RoadOut[]>([])
  const [routeName, setRouteName] = useState('')
  const [createdRoute, setCreatedRoute] = useState<RouteOut | null>(null)
  const [routeCreating, setRouteCreating] = useState(false)
  const [routeError, setRouteError] = useState<string | null>(null)
  const [selectedRoadId, setSelectedRoadId] = useState<string>('')
  const [sequence, setSequence] = useState<string>('1')
  const [addingRoad, setAddingRoad] = useState(false)
  const [addRoadError, setAddRoadError] = useState<string | null>(null)
  const [routeRoads, setRouteRoads] = useState<RouteRoadOut[]>([])

  // Load saved routes on mount
  useEffect(() => {
    loadSavedRoutes()
  }, [])

  // Load roads list for admin create form
  useEffect(() => {
    if (isAdmin) {
      infrastructureApi.getRoads()
        .then(res => setRoads(res.items))
        .catch(console.error)
    }
  }, [isAdmin])

  const loadSavedRoutes = async () => {
    setRoutesLoading(true)
    try {
      const res = await routesApi.listRoutes()
      setSavedRoutes(res.items || [])
    } catch (err) {
      console.error('Failed to load saved routes:', err)
    } finally {
      setRoutesLoading(false)
    }
  }

  const handleViewRoute = async (routeId: number) => {
    setDetailLoading(true)
    try {
      const detail = await routesApi.getRouteDetail(routeId)
      setSelectedRoute(detail)
    } catch (err) {
      console.error('Failed to load route detail:', err)
    } finally {
      setDetailLoading(false)
    }
  }

  const handleCreateRoute = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!routeName.trim()) return

    setRouteCreating(true)
    setRouteError(null)
    setCreatedRoute(null)
    setRouteRoads([])

    try {
      const res = await routesApi.createRoute({ name: routeName })
      setCreatedRoute(res)
      loadSavedRoutes() // Refresh list
    } catch (err: any) {
      setRouteError(err.message || 'Failed to create route')
    } finally {
      setRouteCreating(false)
    }
  }

  const handleAddRoad = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!createdRoute || !selectedRoadId || !sequence) return

    setAddingRoad(true)
    setAddRoadError(null)

    try {
      const res = await routesApi.addRoadToRoute(createdRoute.id, {
        road_id: parseInt(selectedRoadId),
        sequence: parseInt(sequence)
      })
      setRouteRoads([...routeRoads, res].sort((a, b) => a.sequence - b.sequence))
      setSequence((parseInt(sequence) + 1).toString())
    } catch (err: any) {
      setAddRoadError(err.message || 'Failed to add road')
    } finally {
      setAddingRoad(false)
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'blocked': return 'text-red-500'
      case 'restricted': return 'text-amber-500'
      default: return 'text-emerald-500'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'blocked': return <XCircle className="w-4 h-4 text-red-500" />
      case 'restricted': return <AlertTriangle className="w-4 h-4 text-amber-500" />
      default: return <Shield className="w-4 h-4 text-emerald-500" />
    }
  }

  return (
    <div className="container max-w-5xl mx-auto p-4 md:p-8 flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-3">
          <RouteIcon className="w-8 h-8 text-primary" />
          {t('saved_routes.title', 'Saved Routes')}
        </h1>
        <p className="text-muted-foreground mt-2">
          {isAdmin
            ? t('saved_routes.subtitle_admin', 'View, create and manage supply corridor routes.')
            : t('saved_routes.subtitle_user', 'View pre-planned supply corridor routes and their current status.')}
        </p>
      </div>

      {/* ── Saved Routes List (ALL USERS) ── */}
      <div className="bg-card border rounded-lg p-6 shadow-sm">
        <h2 className="font-semibold text-lg border-b pb-2 mb-4">
          {t('saved_routes.all_routes', 'All Saved Routes')}
        </h2>

        {routesLoading ? (
          <p className="text-muted-foreground text-sm">Loading routes...</p>
        ) : savedRoutes.length === 0 ? (
          <p className="text-muted-foreground text-sm">No saved routes yet.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {savedRoutes.map(route => (
              <button
                key={route.id}
                onClick={() => handleViewRoute(route.id)}
                className={`w-full text-left p-3 rounded border flex items-center justify-between hover:bg-muted/50 transition-colors ${
                  selectedRoute?.id === route.id ? 'bg-primary/10 border-primary/30' : 'bg-background'
                }`}
              >
                <div className="flex items-center gap-3">
                  <MapPin className="w-4 h-4 text-primary shrink-0" />
                  <div>
                    <span className="font-medium">{route.name}</span>
                    <span className="text-xs text-muted-foreground ml-2">
                      {route.road_count} roads · {route.total_distance_km} km
                    </span>
                  </div>
                </div>
                <ChevronRight className="w-4 h-4 text-muted-foreground" />
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── Route Detail View (ALL USERS) ── */}
      {selectedRoute && (
        <div className="bg-card border rounded-lg p-6 shadow-sm">
          <div className="flex items-center justify-between border-b pb-2 mb-4">
            <h2 className="font-semibold text-lg">{selectedRoute.name}</h2>
            <div className={`flex items-center gap-1.5 text-sm font-medium ${getStatusColor(selectedRoute.route_status)}`}>
              {getStatusIcon(selectedRoute.route_status)}
              {selectedRoute.route_status.toUpperCase()}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 mb-4 text-sm">
            <div className="bg-muted/50 rounded p-3 text-center">
              <div className="text-2xl font-bold">{selectedRoute.total_distance_km}</div>
              <div className="text-muted-foreground">Total km</div>
            </div>
            <div className="bg-muted/50 rounded p-3 text-center">
              <div className="text-2xl font-bold">{selectedRoute.segments.length}</div>
              <div className="text-muted-foreground">Road segments</div>
            </div>
            <div className="bg-muted/50 rounded p-3 text-center">
              <div className={`text-2xl font-bold ${selectedRoute.blocked_road_count > 0 ? 'text-red-500' : selectedRoute.restricted_road_count > 0 ? 'text-amber-500' : 'text-emerald-500'}`}>
                {selectedRoute.blocked_road_count > 0 ? `${selectedRoute.blocked_road_count} Blocked` : selectedRoute.restricted_road_count > 0 ? `${selectedRoute.restricted_road_count} Restricted` : 'Clear'}
              </div>
              <div className="text-muted-foreground">Hazards</div>
            </div>
          </div>

          {selectedRoute.blocked_road_count > 0 && (
            <div className="p-3 bg-red-500/10 text-red-600 border border-red-500/20 rounded text-sm mb-4 flex gap-2 items-center">
              <XCircle className="w-4 h-4 shrink-0" />
              <span><strong>Warning:</strong> This route has {selectedRoute.blocked_road_count} blocked road(s) due to damage. Consider an alternative route.</span>
            </div>
          )}

          <div className="flex flex-col gap-1">
            {selectedRoute.segments.map((seg, idx) => (
              <div key={seg.id} className={`text-sm p-2 rounded flex items-center justify-between border ${
                seg.road_status === 'blocked' ? 'bg-red-500/5 border-red-500/20' :
                seg.road_status === 'restricted' ? 'bg-amber-500/5 border-amber-500/20' :
                'bg-muted/30'
              }`}>
                <div className="flex items-center gap-2">
                  <span className="font-mono bg-background px-1.5 py-0.5 rounded border text-xs">{seg.sequence}</span>
                  <span className="font-medium">{seg.road_name || `Road ${seg.road_id}`}</span>
                  <span className="text-xs text-muted-foreground">({seg.road_type})</span>
                </div>
                <div className="flex items-center gap-2">
                  {seg.road_length_km && <span className="text-xs text-muted-foreground">{seg.road_length_km.toFixed(1)} km</span>}
                  {getStatusIcon(seg.road_status || 'open')}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Admin Create Section ── */}
      {isAdmin && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div className="bg-card border rounded-lg p-6 shadow-sm flex flex-col gap-4 h-fit">
            <h2 className="font-semibold text-lg border-b pb-2">{t('saved_routes.create_title', '1. Create New Route')}</h2>
            
            <form onSubmit={handleCreateRoute} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium">{t('saved_routes.name', 'Route Name')}</label>
                <input 
                  type="text" 
                  value={routeName}
                  onChange={e => setRouteName(e.target.value)}
                  placeholder={t('saved_routes.name_placeholder', 'e.g. Guwahati Supply Line A')}
                  className="bg-background border rounded p-2 text-sm"
                  required
                />
              </div>
              
              <button 
                type="submit" 
                disabled={routeCreating || !routeName.trim()}
                className="bg-primary text-primary-foreground py-2 rounded font-medium flex items-center justify-center gap-2 hover:bg-primary/90 disabled:opacity-50"
              >
                {routeCreating ? t('saved_routes.creating_btn', 'Creating...') : <><Plus className="w-4 h-4" /> {t('saved_routes.create_btn', 'Create Route')}</>}
              </button>
            </form>

            {routeError && <div className="mt-2"><ErrorState error={routeError} /></div>}

            {createdRoute && (
              <div className="p-3 bg-emerald-500/10 text-emerald-600 border border-emerald-500/20 rounded text-sm flex gap-2 items-start mt-2">
                <Check className="w-4 h-4 shrink-0 mt-0.5" />
                <div className="flex flex-col">
                  <span className="font-bold">{t('saved_routes.create_success', 'Route created successfully!')}</span>
                  <span>{t('saved_routes.id_label', 'ID:')} {createdRoute.id}</span>
                </div>
              </div>
            )}
          </div>

          <div className={`bg-card border rounded-lg p-6 shadow-sm flex flex-col gap-4 transition-opacity ${!createdRoute ? 'opacity-50 pointer-events-none' : ''}`}>
            <h2 className="font-semibold text-lg border-b pb-2">{t('saved_routes.assign_title', '2. Assign Road Sequence')}</h2>
            
            <form onSubmit={handleAddRoad} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium">{t('saved_routes.select_road', 'Select Road')}</label>
                <select 
                  value={selectedRoadId}
                  onChange={e => setSelectedRoadId(e.target.value)}
                  className="bg-background border rounded p-2 text-sm"
                  required
                >
                  <option value="">{t('saved_routes.choose_road', '-- Choose a road --')}</option>
                  {roads.map(r => (
                    <option key={r.id} value={r.id}>
                      {r.name} (ID: {r.id}, {r.district})
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-2">
                <label className="text-sm font-medium">{t('saved_routes.sequence_order', 'Sequence Order')}</label>
                <input 
                  type="number" 
                  min="1"
                  value={sequence}
                  onChange={e => setSequence(e.target.value)}
                  className="bg-background border rounded p-2 text-sm"
                  required
                />
              </div>
              
              <button 
                type="submit" 
                disabled={addingRoad || !selectedRoadId || !sequence}
                className="bg-secondary text-secondary-foreground py-2 rounded font-medium flex items-center justify-center gap-2 hover:bg-secondary/90 disabled:opacity-50"
              >
                {addingRoad ? t('saved_routes.adding_btn', 'Adding...') : t('saved_routes.add_btn', 'Add Road to Route')}
              </button>
            </form>

            {addRoadError && <div className="mt-2"><ErrorState error={addRoadError} /></div>}

            {routeRoads.length > 0 && (
              <div className="mt-4 flex flex-col gap-2">
                <h3 className="font-medium text-sm text-muted-foreground">{t('saved_routes.current_sequence', 'Current Sequence:')}</h3>
                <ul className="flex flex-col gap-1">
                  {routeRoads.map(rr => (
                    <li key={rr.id} className="text-sm p-2 bg-muted rounded flex items-center justify-between border">
                      <div className="flex items-center gap-2">
                        <span className="font-mono bg-background px-1.5 py-0.5 rounded border text-xs">{rr.sequence}</span>
                        <span className="font-medium">{roads.find(r => r.id === rr.road_id)?.name || `Road ${rr.road_id}`}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
