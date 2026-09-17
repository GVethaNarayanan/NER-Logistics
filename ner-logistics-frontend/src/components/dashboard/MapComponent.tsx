import React from 'react'
import { MapContainer, TileLayer, Polyline, CircleMarker, Popup, GeoJSON, useMapEvents } from 'react-leaflet'
import { LatLngTuple, LatLngBounds } from 'leaflet'
import { RoadOut, BridgeOut } from '../../api/infrastructure'
import 'leaflet/dist/leaflet.css'

import { VehicleOut, VehicleLocationHistoryOut } from '../../api/vehicles'
import { useTranslation } from 'react-i18next'

interface MapComponentProps {
  roadGeoJSON: any | null
  totalRoadsInView: number
  currentZoom: number
  onViewportChange?: (bounds: LatLngBounds, zoom: number) => void
  bridges: BridgeOut[]
  onDistrictSelect: (district: string | null) => void
  onRoadSelect?: (road: any | null) => void
  onMapClick?: (lat: number, lng: number) => void
  origin?: LatLngTuple | null
  destination?: LatLngTuple | null
  routeGeoJSON?: any | null
  vehicles?: VehicleOut[]
  selectedVehicleId?: number | null
  onVehicleSelect?: (vehicleId: number | null) => void
  vehicleHistory?: VehicleLocationHistoryOut[]
}

// Map center: NER region approximate center
const NER_CENTER: LatLngTuple = [26.2006, 92.9376]
const DEFAULT_ZOOM = 7

const getRoadColor = (status?: string | null) => {
  if (!status) return '#64748b'
  switch (status.toLowerCase()) {
    case 'open': return '#10b981' // green
    case 'restricted': return '#f59e0b' // amber
    case 'blocked': return '#ef4444' // red
    default: return '#64748b' // slate
  }
}

const getBridgeColor = (condition?: string | null) => {
  if (!condition) return '#64748b'
  switch (condition.toLowerCase()) {
    case 'good': return '#10b981'
    case 'fair': return '#f59e0b'
    case 'poor': return '#ef4444'
    default: return '#64748b'
  }
}

// For bridge markers, since we just have the default icon, we'll use a simple colored circle marker or custom div icon.
// To keep it simple and robust, we'll use CircleMarker instead of image markers.

const MapClickHandler: React.FC<{ onClick?: (lat: number, lng: number) => void }> = ({ onClick }) => {
  useMapEvents({
    click(e) {
      if (onClick) onClick(e.latlng.lat, e.latlng.lng)
    }
  })
  return null
}

const MapMoveHandler: React.FC<{ onChange?: (bounds: LatLngBounds, zoom: number) => void }> = ({ onChange }) => {
  const map = useMapEvents({
    moveend() { if (onChange) onChange(map.getBounds(), map.getZoom()) },
    zoomend() { if (onChange) onChange(map.getBounds(), map.getZoom()) },
  })

  // Trigger initial change
  React.useEffect(() => {
    if (onChange) onChange(map.getBounds(), map.getZoom())
  }, [map, onChange])

  return null
}

export const MapComponent: React.FC<MapComponentProps> = ({ 
  roadGeoJSON,
  totalRoadsInView,
  currentZoom,
  onViewportChange,
  bridges,  
  onDistrictSelect,
  onRoadSelect,
  onMapClick,
  origin,
  destination,
  routeGeoJSON,
  vehicles = [],
  selectedVehicleId = null,
  onVehicleSelect,
  vehicleHistory = []
}) => {
  const { t } = useTranslation()
  return (
    <div className="relative w-full h-full rounded-lg overflow-hidden border">
      {currentZoom < 8 && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-[400] bg-background/95 backdrop-blur border px-4 py-2 rounded-md shadow text-sm">
          Zoom in to view road network (current: {currentZoom}, required: ≥ 8)
        </div>
      )}
      {totalRoadsInView > (roadGeoJSON?.features?.length || 0) && (
        <div className="absolute top-4 right-4 z-[400] bg-amber-500/90 text-white px-3 py-1 rounded text-xs shadow">
          Showing {roadGeoJSON?.features?.length || 0} of {totalRoadsInView} roads
        </div>
      )}
      
      <MapContainer 
        center={NER_CENTER} 
        zoom={currentZoom || DEFAULT_ZOOM} 
        className="w-full h-full z-0"
        scrollWheelZoom={true}
      >
        <MapClickHandler onClick={onMapClick} />
        <MapMoveHandler onChange={onViewportChange} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {roadGeoJSON && (
          <GeoJSON
            key={JSON.stringify(roadGeoJSON).slice(0, 100)} // re-render on data change
            data={roadGeoJSON}
            style={(feature: any) => ({
              color: getRoadColor(feature?.properties?.status),
              weight: feature?.properties?.road_type === 'primary' ? 4 : 
                      feature?.properties?.road_type === 'secondary' ? 3 : 2,
              opacity: 0.8
            })}
            onEachFeature={(feature: any, layer: any) => {
              layer.on({
                click: () => {
                  if (onRoadSelect) onRoadSelect(feature.properties)
                }
              })
              layer.bindPopup(`
                <div class="p-1">
                  <h3 class="font-bold text-sm">${feature.properties.name || 'Unnamed Road'}</h3>
                  <p class="text-xs text-muted-foreground mb-2">OSM ID: ${feature.properties.osm_id || 'N/A'}</p>
                  <div class="flex flex-col gap-1 text-xs">
                    <div class="flex justify-between gap-4">
                      <span class="font-medium">Type:</span>
                      <span class="capitalize">${feature.properties.road_type || 'unknown'}</span>
                    </div>
                    <div class="flex justify-between gap-4">
                      <span class="font-medium">Status:</span>
                      <span class="capitalize font-bold" style="color: ${getRoadColor(feature.properties.status)}">
                        ${feature.properties.status || 'open'}
                      </span>
                    </div>
                  </div>
                </div>
              `)
            }}
          />
        )}

        {bridges.map(bridge => (
          <CircleMarker
            key={`bridge-${bridge.id}`}
            center={[bridge.latitude, bridge.longitude]}
            radius={6}
            pathOptions={{
              fillColor: getBridgeColor(bridge.condition),
              color: '#ffffff',
              weight: 1,
              fillOpacity: 1
            }}
          >
            <Popup>
              <div className="p-1">
                <h3 className="font-bold text-sm">{bridge.name}</h3>
                <div className="flex flex-col gap-1 text-xs mt-2">
                  <div className="flex justify-between gap-4">
                    <span className="font-medium">Condition:</span>
                    <span className="capitalize font-bold" style={{ color: getBridgeColor(bridge.condition) }}>
                      {bridge.condition || 'unverified'}
                    </span>
                  </div>
                </div>
              </div>
            </Popup>
          </CircleMarker>
        ))}

        {vehicleHistory.length > 0 && (
          <Polyline
            positions={vehicleHistory.map(h => [h.latitude, h.longitude])}
            color="#3b82f6"
            weight={4}
            dashArray="10, 10"
            opacity={0.6}
          />
        )}

        {vehicles.map(v => {
          const isSelected = v.id === selectedVehicleId;
          return (
            <CircleMarker
              key={`vehicle-${v.id}`}
              center={[v.current_lat, v.current_lon]}
              radius={isSelected ? 10 : 7}
              pathOptions={{
                color: isSelected ? 'black' : 'white',
                weight: 2,
                fillColor: '#3b82f6',
                fillOpacity: 1
              }}
              eventHandlers={{
                click: () => {
                  if (onVehicleSelect) onVehicleSelect(v.id)
                }
              }}
            >
              <Popup>
                <div className="text-sm">
                  <p className="font-bold">{v.vehicle_number}</p>
                  <p>Status: {v.status}</p>
                  {v.destination && <p>Dest: {v.destination}</p>}
                  <p className="text-xs text-blue-500 font-semibold mt-1">{t('vehicles.simulated_gps', 'SIMULATED GPS')}</p>
                </div>
              </Popup>
            </CircleMarker>
          )
        })}

        {origin && (
          <CircleMarker center={origin} radius={8} pathOptions={{ color: '#3b82f6', fillColor: '#3b82f6', fillOpacity: 1 }}>
            <Popup>Origin</Popup>
          </CircleMarker>
        )}
        {destination && (
          <CircleMarker center={destination} radius={8} pathOptions={{ color: '#ec4899', fillColor: '#ec4899', fillOpacity: 1 }}>
            <Popup>Destination</Popup>
          </CircleMarker>
        )}
        {routeGeoJSON && (
          <GeoJSON 
            data={routeGeoJSON} 
            key={JSON.stringify(routeGeoJSON)}
            style={{ 
              color: routeGeoJSON.properties?.risk_level === 'HIGH' ? '#ef4444' : 
                     routeGeoJSON.properties?.risk_level === 'MEDIUM' ? '#f59e0b' : '#3b82f6', 
              weight: 5,
              opacity: 0.8 
            }}
          />
        )}
      </MapContainer>
      
      {/* Map Legend overlay */}
      <div className="absolute bottom-6 right-6 z-[400] bg-background/95 backdrop-blur border p-3 rounded-md shadow-sm text-xs pointer-events-none">
        <h4 className="font-semibold mb-2">Road Status</h4>
        <div className="flex flex-col gap-1.5 mb-3">
          <div className="flex items-center gap-2"><div className="w-4 h-1 bg-[#10b981] rounded-full" /> Open</div>
          <div className="flex items-center gap-2"><div className="w-4 h-1 bg-[#f59e0b] rounded-full" /> Restricted</div>
          <div className="flex items-center gap-2"><div className="w-4 h-1 bg-[#ef4444] rounded-full" /> Blocked</div>
        </div>
        
        <h4 className="font-semibold mb-2">Bridge Condition</h4>
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2"><div className="w-2.5 h-2.5 bg-[#10b981] rounded-full border border-white" /> Good</div>
          <div className="flex items-center gap-2"><div className="w-2.5 h-2.5 bg-[#f59e0b] rounded-full border border-white" /> Fair</div>
          <div className="flex items-center gap-2"><div className="w-2.5 h-2.5 bg-[#ef4444] rounded-full border border-white" /> Poor</div>
        </div>
      </div>
    </div>
  )
}
