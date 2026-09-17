import React, { useState, useEffect } from 'react'
import { infrastructureApi, RoadOut } from '../api/infrastructure'
import { routesApi, RouteOut, RouteRoadOut } from '../api/routes'
import { AlertCircle, Route as RouteIcon, Plus, Check } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useTranslation } from 'react-i18next'
import { ErrorState } from '../components/shared/ErrorState'

export const SavedRoutes: React.FC = () => {
  const { role } = useAuth()
  const isAdmin = role === 'admin'
  const { t } = useTranslation()

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

  useEffect(() => {
    let isMounted = true
    infrastructureApi.getRoads()
      .then(res => {
        if (isMounted) {
          setRoads(res.items)
        }
      })
      .catch(console.error)
    return () => { isMounted = false }
  }, [])

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

  if (!isAdmin) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-8 text-center text-muted-foreground gap-4">
        <AlertCircle className="w-12 h-12 text-destructive opacity-50" />
        <div>
          <h2 className="text-xl font-bold text-foreground">{t('saved_routes.access_denied', 'Access Denied')}</h2>
          <p>{t('saved_routes.access_denied_msg', 'You do not have permission to manage saved routes. Administrator access is required.')}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="container max-w-4xl mx-auto p-4 md:p-8 flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-3">
          <RouteIcon className="w-8 h-8 text-primary" />
          {t('saved_routes.title', 'Saved Routes')}
        </h1>
        <p className="text-muted-foreground mt-2">{t('saved_routes.subtitle', 'Create static routes and assign geographic road sequences.')}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Route Creation Form */}
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

          {routeError && (
            <div className="mt-2">
              <ErrorState error={routeError} />
            </div>
          )}

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

        {/* Road Sequence Assignment */}
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

          {addRoadError && (
            <div className="mt-2">
              <ErrorState error={addRoadError} />
            </div>
          )}

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
    </div>
  )
}
