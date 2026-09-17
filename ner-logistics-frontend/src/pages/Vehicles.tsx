import React, { useState, useEffect, useMemo } from 'react'
import { vehicleApi, VehicleOut, VehicleLocationHistoryOut } from '../api/vehicles'
import { infrastructureApi, RoadOut, BridgeOut } from '../api/infrastructure'
import { MapComponent } from '../components/dashboard/MapComponent'
import { useAuth } from '../contexts/AuthContext'
import { Truck, Info, Activity } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { ErrorState } from '../components/shared/ErrorState'
import { EmptyState } from '../components/shared/EmptyState'

export const Vehicles: React.FC = () => {
  const { role } = useAuth()
  const isAdmin = role === 'admin'
  const { t } = useTranslation()

  const [vehicles, setVehicles] = useState<VehicleOut[]>([])
  const [vehiclesLoading, setVehiclesLoading] = useState(true)
  const [vehiclesError, setVehiclesError] = useState<string | null>(null)

  const [roads, setRoads] = useState<RoadOut[]>([])
  const [bridges, setBridges] = useState<BridgeOut[]>([])
  
  const [selectedVehicleId, setSelectedVehicleId] = useState<number | null>(null)
  
  const [history, setHistory] = useState<VehicleLocationHistoryOut[]>([])
  const [assignmentRouteId, setAssignmentRouteId] = useState<string>('')
  const [assigningLoading, setAssigningLoading] = useState(false)
  const [assigningError, setAssigningError] = useState<string | null>(null)
  const [assigningSuccess, setAssigningSuccess] = useState(false)

  // Polling for vehicles
  useEffect(() => {
    let isMounted = true

    const fetchVehicles = async (isBackground: boolean) => {
      if (!isBackground) setVehiclesLoading(true)
      try {
        const res = await vehicleApi.getVehicles()
        if (isMounted) {
          setVehicles(res.items)
          setVehiclesError(null)
        }
      } catch (err: any) {
        if (isMounted) setVehiclesError(err.message || 'Failed to load vehicles')
      } finally {
        if (isMounted && !isBackground) setVehiclesLoading(false)
      }
    }

    // Initial fetch
    fetchVehicles(false)

    // Polling interval ~10s
    const interval = setInterval(() => {
      fetchVehicles(true)
    }, 10000)

    return () => {
      isMounted = false
      clearInterval(interval)
    }
  }, [])

  // Initial infrastructure load
  useEffect(() => {
    infrastructureApi.getRoads().then(res => setRoads(res.items)).catch(console.error)
    infrastructureApi.getBridges().then(res => setBridges(res.items)).catch(console.error)
  }, [])

  // Load history when a vehicle is selected
  useEffect(() => {
    if (!selectedVehicleId) {
      setHistory([])
      return
    }

    let isMounted = true
    setAssigningSuccess(false)
    setAssigningError(null)
    setAssignmentRouteId('')

    vehicleApi.getVehicleHistory(selectedVehicleId)
      .then(res => {
        if (isMounted) setHistory(res.items)
      })
      .catch(err => {
        console.error(err)
      })

    return () => { isMounted = false }
  }, [selectedVehicleId])

  const selectedVehicle = useMemo(() => 
    vehicles.find(v => v.id === selectedVehicleId) || null
  , [vehicles, selectedVehicleId])

  const handleAssignRoute = async () => {
    if (!selectedVehicleId || !assignmentRouteId) return

    setAssigningLoading(true)
    setAssigningError(null)
    setAssigningSuccess(false)

    try {
      const res = await vehicleApi.assignRoute(selectedVehicleId, parseInt(assignmentRouteId))
      setAssigningSuccess(true)
      // Update local vehicle state to avoid waiting for next poll
      setVehicles(prev => prev.map(v => v.id === selectedVehicleId ? res : v))
    } catch (err: any) {
      setAssigningError(err.message || 'Failed to assign route')
    } finally {
      setAssigningLoading(false)
    }
  }

  return (
    <div className="flex flex-col lg:flex-row h-auto lg:h-[calc(100vh-4rem)] min-h-[calc(100vh-4rem)] p-4 gap-4 bg-muted/20">
      
      {/* Sidebar Panel */}
      <div className="w-full lg:w-96 flex flex-col gap-4 order-2 lg:order-1 overflow-y-auto pb-4">
        
        {/* Vehicle List */}
        <div className="bg-card border rounded-lg p-4 shadow-sm flex flex-col gap-4 flex-1">
          <div className="flex items-center justify-between">
            <h2 className="font-bold flex items-center gap-2">
              <Truck className="w-5 h-5 text-primary" />
              Fleet Status
            </h2>
            {vehiclesLoading && <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />}
          </div>

          {vehiclesError && (
            <div className="mt-2">
              <ErrorState error={vehiclesError} onRetry={() => setVehiclesError(null)} />
            </div>
          )}

          {!vehiclesLoading && !vehiclesError && vehicles.length === 0 && (
            <EmptyState title={t('vehicles.no_vehicles', 'No vehicles found.')} icon={<Truck className="w-8 h-8" />} />
          )}

          <div className="flex flex-col gap-2 overflow-y-auto">
            {vehicles.map(v => (
              <button
                key={v.id}
                onClick={() => setSelectedVehicleId(v.id === selectedVehicleId ? null : v.id)}
                className={`flex flex-col text-left p-3 border rounded transition-colors ${
                  v.id === selectedVehicleId ? 'ring-2 ring-primary border-primary bg-primary/5' : 'hover:bg-muted'
                }`}
              >
                <div className="flex items-center justify-between w-full">
                  <span className="font-bold text-sm">{v.vehicle_number}</span>
                  <span className={`text-xs px-2 py-0.5 rounded font-medium ${
                    v.status === 'idle' ? 'bg-muted text-muted-foreground' : 
                    v.status === 'in_transit' ? 'bg-emerald-500/10 text-emerald-600' : 
                    'bg-amber-500/10 text-amber-600'
                  }`}>
                    {v.status}
                  </span>
                </div>
                <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
                  <span>{v.speed_kmh?.toFixed(0) || 0} km/h</span>
                  <span className="font-semibold text-blue-500">{t('vehicles.simulated_gps', 'SIMULATED GPS')}</span>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Selected Vehicle Detail */}
        {selectedVehicle && (
          <div className="bg-card border rounded-lg p-4 shadow-sm flex flex-col gap-4">
            <h3 className="font-semibold text-sm flex items-center gap-2 border-b pb-2">
              <Info className="w-4 h-4 text-primary" />
              Vehicle Details: {selectedVehicle.vehicle_number}
            </h3>

            <div className="grid grid-cols-2 gap-y-3 text-sm">
              <span className="text-muted-foreground">Status:</span>
              <span className="font-medium capitalize">{selectedVehicle.status}</span>
              
              <span className="text-muted-foreground">Speed:</span>
              <span className="font-medium">{selectedVehicle.speed_kmh?.toFixed(1) || 0} km/h</span>
              
              <span className="text-muted-foreground">Destination:</span>
              <span className="font-medium truncate">{selectedVehicle.destination || 'None'}</span>
              
              <span className="text-muted-foreground">Coordinates:</span>
              <span className="font-medium font-mono text-xs">
                {selectedVehicle.current_lat.toFixed(4)}, {selectedVehicle.current_lon.toFixed(4)}
              </span>
              
              <span className="text-muted-foreground">Route ID:</span>
              <span className="font-medium">{selectedVehicle.current_route_id || 'None'}</span>

              {selectedVehicle.current_route_id && (
                <>
                  <span className="text-muted-foreground">Route Progress:</span>
                  <span className="font-medium">{selectedVehicle.current_route_progress_km?.toFixed(1) || 0} km</span>
                </>
              )}
            </div>

            {isAdmin && (
              <div className="mt-2 pt-4 border-t flex flex-col gap-2">
                <span className="text-xs font-bold text-muted-foreground">ADMIN: ROUTE ASSIGNMENT</span>
                <div className="flex gap-2">
                  <input
                    type="number"
                    placeholder="Route ID"
                    value={assignmentRouteId}
                    onChange={(e) => setAssignmentRouteId(e.target.value)}
                    className="flex-1 bg-background border rounded px-3 py-1.5 text-sm"
                  />
                  <button
                    onClick={handleAssignRoute}
                    disabled={!assignmentRouteId || assigningLoading}
                    className="bg-primary text-primary-foreground px-4 py-1.5 rounded text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
                  >
                    {assigningLoading ? 'Assigning...' : 'Assign'}
                  </button>
                </div>
                {assigningError && (
                  <div className="mt-2">
                    <ErrorState error={assigningError} onRetry={() => setAssigningError(null)} />
                  </div>
                )}
                {assigningSuccess && <span className="text-xs text-emerald-500">Route assigned successfully!</span>}
              </div>
            )}

            <div className="mt-2 p-2 bg-blue-500/10 rounded border border-blue-500/20 text-xs flex gap-2">
              <Activity className="w-4 h-4 text-blue-500 shrink-0" />
              <div className="flex flex-col">
                <span className="font-bold text-blue-600">{t('vehicles.simulated_provenance_title', 'SIMULATED DATA PROVENANCE')}</span>
                <span className="text-blue-600/80">
                  {t('vehicles.simulated_provenance_desc', 'Vehicle location data is simulated by the backend in V1 and is not live physical GPS telemetry.')}
                </span>
              </div>
            </div>
          </div>
        )}

      </div>

      {/* Main Map Area */}
      <div className="flex-1 bg-card rounded-lg shadow-sm border overflow-hidden order-1 lg:order-2 min-h-[400px]">
        <MapComponent 
          roads={roads} 
          bridges={bridges} 
          onDistrictSelect={() => {}}
          vehicles={vehicles}
          selectedVehicleId={selectedVehicleId}
          onVehicleSelect={setSelectedVehicleId}
          vehicleHistory={history}
        />
      </div>
      
    </div>
  )
}
