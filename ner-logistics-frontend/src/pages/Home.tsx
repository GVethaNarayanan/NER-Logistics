import React, { useState, useEffect, useMemo, useCallback } from 'react'
import { infrastructureApi, RoadOut, BridgeOut } from '../api/infrastructure'
import { vehicleApi, VehicleOut } from '../api/vehicles'
import { routingApi, RouteResponse } from '../api/routing'
import { ApiError } from '../api/client'
import { ErrorState } from '../components/shared/ErrorState'
import { MapComponent, TargetMapView } from '../components/dashboard/MapComponent'
import { ConnectivityPanel } from '../components/dashboard/ConnectivityPanel'
import { RiskPanel } from '../components/dashboard/RiskPanel'
import { RoutePlannerPanel } from '../components/dashboard/RoutePlannerPanel'
import { AlertCircle } from 'lucide-react'
import { LatLngTuple, LatLngBounds } from 'leaflet'
import { useRegion } from '../contexts/RegionContext'
import { NavigationHUD } from '../components/dashboard/NavigationHUD'
import {
  generateManeuvers,
  calculateNavigationProgress,
  navigationVoice,
  NavigationProgress,
  ManeuverStep,
} from '../lib/navigation'

const STATE_CENTERS: Record<string, { center: LatLngTuple; zoom: number }> = {
  'Assam': { center: [26.2006, 92.9376], zoom: 7 },
  'Arunachal Pradesh': { center: [28.2180, 94.7278], zoom: 7 },
  'Manipur': { center: [24.6637, 93.9063], zoom: 8 },
  'Meghalaya': { center: [25.4670, 91.3662], zoom: 8 },
  'Mizoram': { center: [23.1645, 92.9376], zoom: 8 },
  'Nagaland': { center: [26.1584, 94.5624], zoom: 8 },
  'Sikkim': { center: [27.5330, 88.5122], zoom: 8 },
  'Tripura': { center: [23.9408, 91.9882], zoom: 8 },
}


export const Home: React.FC = () => {
  // Shared region context (persists across page navigation)
  const {
    registryStates, registryLoading, registryError,
    selectedStateId, setSelectedStateId,
    selectedDistrictId, setSelectedDistrictId,
    activeState, availableDistricts, activeDistrict,
  } = useRegion()

  const [roads, setRoads] = useState<RoadOut[]>([])
  const [bridges, setBridges] = useState<BridgeOut[]>([])
  const [vehicles, setVehicles] = useState<VehicleOut[]>([])
  
  const [roadsLoading, setRoadsLoading] = useState(false)
  const [bridgesLoading, setBridgesLoading] = useState(false)
  
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

  // Active Driver Navigation State
  const [isNavigating, setIsNavigating] = useState(false)
  const [isVoiceMuted, setIsVoiceMuted] = useState(false)
  const [isSimulationMode, setIsSimulationMode] = useState(true)
  const [isSimulationPaused, setIsSimulationPaused] = useState(false)
  const [isAutoFollow, setIsAutoFollow] = useState(true)
  const [maneuvers, setManeuvers] = useState<ManeuverStep[]>([])
  const [simIndex, setSimIndex] = useState(0)
  const [navProgress, setNavProgress] = useState<NavigationProgress>({
    currentLat: 0,
    currentLon: 0,
    heading: 0,
    speedKmh: 45,
    currentStepIndex: 0,
    distanceToNextTurnMeters: 0,
    nextManeuver: null,
    totalDistanceRemainingKm: 0,
    estimatedTimeRemainingMinutes: 0,
    upcomingBridgeAlert: null,
    isOffRoute: false,
  })

  // Registry is loaded by RegionContext — no local useEffect needed

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

  // Live vehicles polling (every 10s)
  useEffect(() => {
    let isMounted = true

    const fetchVehicles = async () => {
      try {
        const res = await vehicleApi.getVehicles()
        if (isMounted) setVehicles(res.items)
      } catch (err) {
        console.error('Failed to load live vehicles on dashboard:', err)
      }
    }

    fetchVehicles()
    const interval = setInterval(fetchVehicles, 10000)

    return () => {
      isMounted = false
      clearInterval(interval)
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
    const timer = setTimeout(() => {
      setRoadsLoading(true)
      setRoadsError(null)
      infrastructureApi.getRoadsBbox({
        minLon: sw.lng, minLat: sw.lat,
        maxLon: ne.lng, maxLat: ne.lat,
        zoom: viewport.zoom,
        districtId: selectedDistrictId,
        limit: 2000
      }).then(result => {
        if (isMounted) {
          setRoadGeoJSON({ type: "FeatureCollection", features: result.features })
          setTotalRoadsInView(result.total_matched)
          setRoadsError(null)
        }
      }).catch(err => {
        if (isMounted) {
          console.warn('Roads viewport fetch delayed:', err)
        }
      }).finally(() => {
        if (isMounted) setRoadsLoading(false)
      })
    }, 250)

    return () => {
      isMounted = false
      clearTimeout(timer)
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

      // Snap origin and destination to the exact first and last coordinates of the road route
      const coords = result.geometry?.coordinates as [number, number][]
      if (coords && coords.length >= 2) {
        setOrigin([coords[0][1], coords[0][0]])
        const last = coords[coords.length - 1]
        setDestination([last[1], last[0]])
      }
    } catch (err: any) {
      setRouteError(err.message || 'Routing failed')
    } finally {
      setRouteLoading(false)
    }
  }, [origin, destination])

  // Navigation Start / Stop Handlers
  const handleStartNavigation = useCallback(() => {
    if (!routeResult || !routeResult.geometry || !routeResult.geometry.coordinates) return

    const coords = routeResult.geometry.coordinates as [number, number][]
    if (coords.length < 2) return

    const bridgesOnRoute = (routeResult.properties as any).bridges || []
    const totalDistKm = (routeResult.properties as any).total_distance_km
    const totalDurMin = (routeResult.properties as any).estimated_duration_minutes

    navigationVoice.reset()
    const generated = generateManeuvers(coords, bridgesOnRoute)
    setManeuvers(generated)
    setIsNavigating(true)
    setIsAutoFollow(true)
    setSimIndex(0)

    const initialLat = coords[0][1]
    const initialLon = coords[0][0]
    const initialProgress = calculateNavigationProgress(
      initialLat,
      initialLon,
      coords,
      generated,
      bridgesOnRoute,
      40,
      totalDistKm,
      totalDurMin
    )
    setNavProgress(initialProgress)

    navigationVoice.speakImmediate('Starting navigation to destination. Follow the highlighted corridor.', isVoiceMuted)
  }, [routeResult, isVoiceMuted])

  const handleStopNavigation = useCallback(() => {
    setIsNavigating(false)
    navigationVoice.reset()
    navigationVoice.speakImmediate('Navigation ended.', isVoiceMuted)
  }, [isVoiceMuted])

  // Active Navigation tracking (Real GPS vs Simulation Drive)
  useEffect(() => {
    if (!isNavigating || !routeResult?.geometry?.coordinates) return

    const coords = routeResult.geometry.coordinates as [number, number][]
    const bridgesOnRoute = (routeResult.properties as any).bridges || []
    const totalDistKm = (routeResult.properties as any).total_distance_km
    const totalDurMin = (routeResult.properties as any).estimated_duration_minutes

    if (!isSimulationMode) {
      // ── Real Device Hardware GPS ──────────────────────────────────────────
      if (!('geolocation' in navigator)) {
        setIsSimulationMode(true)
        return
      }

      const watchId = navigator.geolocation.watchPosition(
        (pos) => {
          const lat = pos.coords.latitude
          const lon = pos.coords.longitude
          const hwSpeed =
            pos.coords.speed !== null && pos.coords.speed !== undefined
              ? Math.max(10, Math.round(pos.coords.speed * 3.6))
              : navProgress.speedKmh || 40

          const prog = calculateNavigationProgress(
            lat,
            lon,
            coords,
            maneuvers,
            bridgesOnRoute,
            hwSpeed,
            totalDistKm,
            totalDurMin
          )
          if (pos.coords.heading !== null && !isNaN(pos.coords.heading)) {
            prog.heading = pos.coords.heading
          }
          setNavProgress(prog)
          navigationVoice.checkAndSpeak(prog, isVoiceMuted)
        },
        (err) => {
          console.warn('Device GPS tracking:', err)
        },
        { enableHighAccuracy: true, maximumAge: 1000, timeout: 10000 }
      )

      return () => {
        navigator.geolocation.clearWatch(watchId)
      }
    } else {
      // ── Simulation Drive Mode ────────────────────────────────────────────
      if (isSimulationPaused) return

      // Pacing dynamically matches speed:
      // When slowing down into a corner (20 km/h), tick is 1800ms (lingers in turn).
      // When cruising on straight highways (58 km/h), tick is 850ms (moves briskly).
      const currentSpeed = navProgress.speedKmh || 40
      const tickDelay = Math.round(Math.max(850, Math.min(1850, (3600 / Math.max(15, currentSpeed)) * 10)))

      const timer = setTimeout(() => {
        setSimIndex((prev) => {
          if (prev >= coords.length - 1) {
            // Already at destination - remain safely stopped at end of route
            setIsSimulationPaused(true)
            return prev
          }

          const nextIdx = prev + 1
          const pt = coords[nextIdx]
          const lat = pt[1]
          const lon = pt[0]

          const isAtDestination = nextIdx >= coords.length - 1

          const prog = calculateNavigationProgress(
            lat,
            lon,
            coords,
            maneuvers,
            bridgesOnRoute,
            isAtDestination ? 0 : currentSpeed,
            totalDistKm,
            totalDurMin
          )

          if (isAtDestination) {
            prog.speedKmh = 0
            prog.totalDistanceRemainingKm = 0.0
            prog.estimatedTimeRemainingMinutes = 0
            prog.distanceToNextTurnMeters = 0
            prog.nextManeuver = {
              id: 'step-destination',
              instruction: 'Destination Arrived',
              type: 'destination',
              distanceMeters: 0,
              roadName: 'Destination',
              lat,
              lon,
              bearing: prog.heading,
              coordIndex: coords.length - 1,
              cumulativeDistMeters: 0,
            }
            setIsSimulationPaused(true)
            navigationVoice.speakImmediate('You have safely arrived at your destination.', isVoiceMuted)
          } else {
            navigationVoice.checkAndSpeak(prog, isVoiceMuted)
          }

          setNavProgress(prog)
          return nextIdx
        })
      }, tickDelay)

      return () => clearTimeout(timer)
    }
  }, [isNavigating, isSimulationMode, isSimulationPaused, routeResult, maneuvers, isVoiceMuted, simIndex, navProgress.speedKmh])

  // Derived filtered items
  const visibleRoads = roads
  const visibleBridges = bridges

  const handleDistrictChange = (id: number | string | null) => {
    if (id === null || id === '' || id === 'none') {
      setSelectedDistrictId(null)
    } else if (id === 'all') {
      setSelectedDistrictId(null)
    } else if (id === 'unassigned') {
      setSelectedDistrictId(-1)
    } else {
      setSelectedDistrictId(id as number)
    }
    setSelectedRoad(null)
  }

  const selectedDistrict = availableDistricts.find(d => d.id === selectedDistrictId)
  const selectedState = registryStates.find(s => s.id === selectedStateId)

  const targetView: TargetMapView | null = useMemo(() => {
    if (selectedDistrict && selectedDistrict.centroid_lat && selectedDistrict.centroid_lon) {
      return {
        center: [selectedDistrict.centroid_lat, selectedDistrict.centroid_lon],
        zoom: 11,
        key: `dist_${selectedDistrict.id}`
      }
    }
    if (selectedState && STATE_CENTERS[selectedState.name]) {
      const sc = STATE_CENTERS[selectedState.name]
      return {
        center: sc.center,
        zoom: sc.zoom,
        key: `state_${selectedState.id}`
      }
    }
    return null
  }, [selectedDistrict, selectedState])

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
                    setSelectedDistrictId(null)
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
                  value={selectedDistrictId === null ? '' : selectedDistrictId === -1 ? 'unassigned' : selectedDistrictId}
                  onChange={(e) => handleDistrictChange(e.target.value === '' || e.target.value === 'all' || e.target.value === 'unassigned' ? e.target.value : parseInt(e.target.value))}
                  className="w-full h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                  disabled={!selectedStateId || availableDistricts.length === 0}
                >
                  <option value="">Select a District</option>
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
          onStartNavigation={handleStartNavigation}
          isNavigating={isNavigating}
          onSetRoutePresets={(orig, dest) => {
            setOrigin(orig)
            setDestination(dest)
            setSelectingMode(null)
          }}
        />
        
        {/* Layer Status Warnings */}
        {(roadsError || bridgesError) && (
          <div className="bg-card border rounded-lg p-4 shadow-sm flex flex-col gap-2">
            <h3 className="font-semibold text-sm flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-amber-500" />
              Layer Status
            </h3>
            {roadsError && <div className="mt-1"><ErrorState error={roadsError} /></div>}
            {bridgesError && <div className="mt-1"><ErrorState error={bridgesError} /></div>}
          </div>
        )}
      </div>

      {/* Main Map Area */}
      <div className="relative flex-1 bg-card rounded-lg shadow-sm border overflow-hidden order-1 lg:order-2 min-h-[400px]">
        {/* Navigation Heads-Up Display Overlay */}
        <NavigationHUD
          progress={navProgress}
          isNavigating={isNavigating}
          onStopNavigation={handleStopNavigation}
          isVoiceMuted={isVoiceMuted}
          onToggleVoice={() => setIsVoiceMuted(!isVoiceMuted)}
          isSimulationMode={isSimulationMode}
          onToggleSimulationMode={() => setIsSimulationMode(!isSimulationMode)}
          isSimulationPaused={isSimulationPaused}
          onToggleSimulationPause={() => {
            const coordsLen = (routeResult?.geometry?.coordinates as any[])?.length || 1
            if (simIndex >= coordsLen - 1) {
              setSimIndex(0)
              setIsSimulationPaused(false)
            } else {
              setIsSimulationPaused(!isSimulationPaused)
            }
          }}
          onRecenter={() => setIsAutoFollow(true)}
          isAutoFollow={isAutoFollow}
        />

        <MapComponent 
          roadGeoJSON={roadGeoJSON} 
          totalRoadsInView={totalRoadsInView}
          currentZoom={viewport.zoom}
          onViewportChange={handleViewportChange}
          bridges={visibleBridges} 
          vehicles={vehicles}
          onDistrictSelect={() => {}}
          onRoadSelect={setSelectedRoad}
          onMapClick={handleMapClick}
          origin={origin}
          destination={destination}
          routeGeoJSON={routeResult}
          targetView={targetView}
          navigatingUser={{
            lat: navProgress.currentLat,
            lon: navProgress.currentLon,
            heading: navProgress.heading,
            speedKmh: navProgress.speedKmh,
            isNavigating,
            isAutoFollow,
          }}
        />

        {roadsLoading && (
          <div className="absolute top-4 left-4 z-[400] bg-background/90 backdrop-blur border px-3 py-1.5 rounded-full shadow-md flex items-center gap-2 text-xs font-medium text-muted-foreground pointer-events-none">
            <div className="w-3 h-3 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            <span>Loading road network...</span>
          </div>
        )}
      </div>
      
    </div>
  )
}
