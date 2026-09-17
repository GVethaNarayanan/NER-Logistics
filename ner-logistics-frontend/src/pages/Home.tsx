import React, { useState, useEffect, useMemo, useCallback } from 'react'
import { infrastructureApi, RoadOut, BridgeOut, StateBase, DistrictBase } from '../api/infrastructure'
import { routingApi, RouteResponse } from '../api/routing'
import { ApiError } from '../api/client'
import { ErrorState } from '../components/shared/ErrorState'
import { MapComponent } from '../components/dashboard/MapComponent'
import { ConnectivityPanel } from '../components/dashboard/ConnectivityPanel'
import { RiskPanel } from '../components/dashboard/RiskPanel'
import { RoutePlannerPanel } from '../components/dashboard/RoutePlannerPanel'
import { AlertCircle } from 'lucide-react'
import { LatLngTuple, LatLngBounds } from 'leaflet'


export const Home: React.FC = () => {
  const [registryStates, setRegistryStates] = useState<StateBase[]>([])
  const [selectedStateId, setSelectedStateId] = useState<number | null>(null)
  const [selectedDistrictId, setSelectedDistrictId] = useState<number | null>(null)

  const [roads, setRoads] = useState<RoadOut[]>([])
  const [bridges, setBridges] = useState<BridgeOut[]>([])
  
  const [registryLoading, setRegistryLoading] = useState(true)
  const [roadsLoading, setRoadsLoading] = useState(false)
  const [bridgesLoading, setBridgesLoading] = useState(false)
  
  const [registryError, setRegistryError] = useState<string | null>(null)
  const [roadsError, setRoadsError] = useState<string | null>(null)
  const [bridgesError, setBridgesError] = useState<string | null>(null)

  const [selectedRoad, setSelectedRoad] = useState<any | null>(null)

  const [viewport, setViewport] = useState<{bounds: LatLngBounds | null, zoom: number}>({ bounds: null, zoom: 7 })
  const [roadGeoJSON, setRoadGeoJSON] = useState<any>(null)
  const [totalRoadsInView, setTotalRoadsInView] = useState(0)

  // Use a ref to store the latest timeout ID
  const timeoutRef = React.useRef<NodeJS.Timeout | null>(null)

  // Debounced viewport change handler
  const handleViewportChange = useCallback((bounds: LatLngBounds, zoom: number) => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
    }
    timeoutRef.current = setTimeout(() => {
      setViewport({ bounds, zoom })
    }, 400)
  }, [])

  // Routing State
  const [origin, setOrigin] = useState<LatLngTuple | null>(null)
  const [destination, setDestination] = useState<LatLngTuple | null>(null)
  const [selectingMode, setSelectingMode] = useState<'origin' | 'destination' | null>(null)
  const [routeLoading, setRouteLoading] = useState(false)
  const [routeError, setRouteError] = useState<string | null>(null)
  const [routeResult, setRouteResult] = useState<RouteResponse | null>(null)

  // Derived Active District Object
  const activeState = useMemo(() => registryStates.find(s => s.id === selectedStateId), [registryStates, selectedStateId])
  const availableDistricts = useMemo(() => activeState ? activeState.districts : [], [activeState])
  const activeDistrict = useMemo(() => availableDistricts.find(d => d.id === selectedDistrictId), [availableDistricts, selectedDistrictId])

  // Initial load of Registry
  useEffect(() => {
    let isMounted = true
    setRegistryLoading(true)
    infrastructureApi.getRegistry()
      .then(res => {
        if (isMounted) {
          setRegistryStates(res.states)
          // Default to first state and first district if available
          if (res.states.length > 0) {
            setSelectedStateId(res.states[0].id)
            if (res.states[0].districts.length > 0) {
              setSelectedDistrictId(res.states[0].districts[0].id)
            }
          }
        }
      })
      .catch(err => {
        if (isMounted) setRegistryError(err instanceof ApiError ? err.message : 'Failed to load registry')
      })
      .finally(() => {
        if (isMounted) setRegistryLoading(false)
      })

    return () => {
      isMounted = false
    }
  }, [])

  // Load infrastructure when selectedDistrictId changes
  useEffect(() => {
    let isMounted = true

    // Load bridges (all for now)
    setBridgesLoading(true)
    infrastructureApi.getBridges()
      .then(res => {
        if (isMounted) setBridges(res.items)
      })
      .catch(err => {
        if (isMounted) setBridgesError(err instanceof ApiError ? err.message : 'Failed to load bridges')
      })
      .finally(() => {
        if (isMounted) setBridgesLoading(false)
      })

    return () => {
      isMounted = false
    }
  }, [])

  // Viewport based road fetching
  useEffect(() => {
    if (!viewport.bounds || viewport.zoom < 8) {
      setRoadGeoJSON(null)
      setTotalRoadsInView(0)
      return
    }

    const sw = viewport.bounds.getSouthWest()
    const ne = viewport.bounds.getNorthEast()

    let isMounted = true
    setRoadsLoading(true)

    infrastructureApi.getRoadsBbox({
      minLon: sw.lng, minLat: sw.lat,
      maxLon: ne.lng, maxLat: ne.lat,
      zoom: viewport.zoom,
      districtId: selectedDistrictId,
      limit: 1000
    }).then(result => {
      if (isMounted) {
        setRoadGeoJSON({ type: "FeatureCollection", features: result.features })
        setTotalRoadsInView(result.total_matched)
      }
    }).catch(err => {
      if (isMounted) setRoadsError(err instanceof ApiError ? err.message : 'Failed to load roads')
    }).finally(() => {
      if (isMounted) setRoadsLoading(false)
    })

    return () => {
      isMounted = false
    }
  }, [viewport.bounds, viewport.zoom, selectedDistrictId])

  const handleMapClick = useCallback((lat: number, lng: number) => {
    if (selectingMode === 'origin') {
      setOrigin([lat, lng])
      setSelectingMode(null)
    } else if (selectingMode === 'destination') {
      setDestination([lat, lng])
      setSelectingMode(null)
    }
  }, [selectingMode])

  const handleCalculateRoute = useCallback(async (preference: 'shortest' | 'safest') => {
    if (!origin || !destination) return

    setRouteLoading(true)
    setRouteError(null)
    setRouteResult(null)

    try {
      const result = await routingApi.computeRoute({
        origin_lat: origin[0],
        origin_lon: origin[1],
        destination_lat: destination[0],
        destination_lon: destination[1],
        preference
      })
      setRouteResult(result)
    } catch (err: any) {
      setRouteError(err.message || 'Routing failed')
    } finally {
      setRouteLoading(false)
    }
  }, [origin, destination])

  // Derived filtered items
  const visibleRoads = roads
  const visibleBridges = bridges

  const handleDistrictChange = (id: number | string | null) => {
    if (id === 'all') {
      setSelectedDistrictId(null)
    } else if (id === 'unassigned') {
      setSelectedDistrictId(-1)
    } else {
      setSelectedDistrictId(id as number)
    }
    setSelectedRoad(null)
  }

  return (
    <div className="flex flex-col lg:flex-row h-auto lg:h-[calc(100vh-4rem)] min-h-[calc(100vh-4rem)] p-4 gap-4 bg-muted/20">
      
      {/* Sidebar Panel */}
      <div className="w-full lg:w-96 flex flex-col gap-4 order-2 lg:order-1 overflow-y-auto pb-4">
        
        {/* District Selector Panel */}
        <div className="bg-card rounded-lg border shadow-sm p-4">
          <h2 className="text-lg font-semibold mb-3">NER Coverage</h2>
          {registryLoading ? (
            <div className="text-sm text-muted-foreground animate-pulse">Loading regions...</div>
          ) : registryError ? (
            <ErrorState error={registryError} />
          ) : (
            <div className="flex flex-col gap-3">
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">State</label>
                <select
                  value={selectedStateId || ''}
                  onChange={(e) => {
                    const sid = parseInt(e.target.value) || null
                    setSelectedStateId(sid)
                    // Reset district when state changes
                    const newState = registryStates.find(s => s.id === sid)
                    setSelectedDistrictId(newState && newState.districts.length > 0 ? newState.districts[0].id : null)
                  }}
                  className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                >
                  <option value="">Select a State</option>
                  <option value="all">All NER</option>
                  {registryStates.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>
              
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">District</label>
                <select
                  value={selectedDistrictId === null ? 'all' : selectedDistrictId === -1 ? 'unassigned' : selectedDistrictId}
                  onChange={(e) => handleDistrictChange(e.target.value === 'all' || e.target.value === 'unassigned' ? e.target.value : parseInt(e.target.value))}
                  className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  disabled={!selectedStateId || availableDistricts.length === 0}
                >
                  <option value="all">All Districts</option>
                  <option value="unassigned">Unassigned / Unresolved</option>
                  {availableDistricts.map(d => (
                    <option key={d.id} value={d.id}>{d.name}</option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </div>

        {selectedDistrictId !== null && selectedDistrictId !== -1 && (
          <ConnectivityPanel 
            selectedDistrictId={selectedDistrictId}
          />
        )}

        <RiskPanel selectedRoad={selectedRoad} />

        <RoutePlannerPanel 
          origin={origin}
          destination={destination}
          selectingMode={selectingMode}
          setSelectingMode={setSelectingMode}
          onCalculateRoute={handleCalculateRoute}
          routeLoading={routeLoading}
          routeError={routeError}
          routeResult={routeResult}
        />
        
        {/* Layer Status Warnings */}
        {(roadsError || bridgesError || (roads.length === 0 && !roadsLoading) || (bridges.length === 0 && !bridgesLoading)) && (
          <div className="bg-card border rounded-lg p-4 shadow-sm flex flex-col gap-2">
            <h3 className="font-semibold text-sm flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-amber-500" />
              Layer Status
            </h3>
            {roadsError && <div className="mt-1"><ErrorState error={roadsError} /></div>}
            {bridgesError && <div className="mt-1"><ErrorState error={bridgesError} /></div>}
            {!roadsError && roads.length === 0 && !roadsLoading && <p className="text-xs text-muted-foreground">No roads returned by server.</p>}
            {!bridgesError && bridges.length === 0 && !bridgesLoading && <p className="text-xs text-muted-foreground">No bridges returned by server.</p>}
          </div>
        )}
      </div>

      {/* Main Map Area */}
      <div className="flex-1 bg-card rounded-lg shadow-sm border overflow-hidden order-1 lg:order-2 min-h-[400px]">
        {(roadsLoading && bridgesLoading) ? (
          <div className="flex w-full h-full items-center justify-center">
            <div className="text-muted-foreground animate-pulse flex flex-col items-center gap-4">
              <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
              <p>Loading NER Infrastructure...</p>
            </div>
          </div>
        ) : (
          <MapComponent 
            roadGeoJSON={roadGeoJSON} 
            totalRoadsInView={totalRoadsInView}
            currentZoom={viewport.zoom}
            onViewportChange={handleViewportChange}
            bridges={visibleBridges} 
            onDistrictSelect={() => {}}
            onRoadSelect={setSelectedRoad}
            onMapClick={handleMapClick}
            origin={origin}
            destination={destination}
            routeGeoJSON={routeResult}
          />
        )}
      </div>
      
    </div>
  )
}
