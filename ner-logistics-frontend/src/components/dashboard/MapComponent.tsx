import React from 'react'
import { MapContainer, TileLayer, Polyline, CircleMarker, Marker, Popup, GeoJSON, useMapEvents, useMap } from 'react-leaflet'
import L, { LatLngTuple, LatLngBounds } from 'leaflet'
import { RoadOut, BridgeOut } from '../../api/infrastructure'
import 'leaflet/dist/leaflet.css'

import { VehicleOut, VehicleLocationHistoryOut } from '../../api/vehicles'
import { useTranslation } from 'react-i18next'

export interface TargetMapView {
  center: LatLngTuple
  zoom: number
  key: string | number
}

const createDirectionalIcon = (heading: number) => {
  return L.divIcon({
    className: 'driver-nav-marker',
    html: `
      <div style="transform: rotate(${heading}deg); transform-origin: center center; display: flex; align-items: center; justify-content: center; width: 44px; height: 44px;">
        <div style="position: absolute; width: 44px; height: 44px; background: rgba(16, 185, 129, 0.28); border-radius: 50%;"></div>
        <div style="position: absolute; width: 32px; height: 32px; background: #059669; border: 3px solid #ffffff; border-radius: 50%; box-shadow: 0 4px 10px rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center;">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="#ffffff" style="margin-top: -2px;">
            <path d="M12 2L4.5 20.29l.71.71L12 18l6.79 3 .71-.71z"/>
          </svg>
        </div>
      </div>
    `,
    iconSize: [44, 44],
    iconAnchor: [22, 22],
  })
}

const createOriginLandmarkIcon = () => {
  return L.divIcon({
    className: 'custom-landmark-pin',
    html: `
      <div style="position: relative; width: 38px; height: 50px; display: flex; flex-direction: column; align-items: center; filter: drop-shadow(0 4px 10px rgba(0,0,0,0.5)); cursor: pointer;">
        <!-- Floating Pill Badge -->
        <div style="position: absolute; top: -16px; background: #065f46; color: #ecfdf5; font-size: 9px; font-weight: 900; padding: 2px 7px; border-radius: 9999px; letter-spacing: 0.5px; white-space: nowrap; border: 1.5px solid #ffffff; box-shadow: 0 2px 6px rgba(0,0,0,0.3);">
          📍 START (A)
        </div>
        <!-- 3D Emerald Teardrop Pin -->
        <svg width="38" height="48" viewBox="0 0 38 48" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M19 0C8.50659 0 0 8.50659 0 19C0 29.5 14.5 43.5 18.0588 47.1765C18.5765 47.7118 19.4235 47.7118 19.9412 47.1765C23.5 43.5 38 29.5 38 19C38 8.50659 29.4934 0 19 0Z" fill="#047857"/>
          <path d="M19 2C9.61116 2 2 9.61116 2 19C2 28 15.5 41 18.5 44.5C18.77 44.8 19.23 44.8 19.5 44.5C22.5 41 36 28 36 19C36 9.61116 28.3888 2 19 2Z" fill="#10b981"/>
          <circle cx="19" cy="18" r="11" fill="#ffffff" stroke="#047857" stroke-width="2"/>
          <text x="19" y="23" font-size="13" font-weight="900" fill="#065f46" text-anchor="middle" font-family="system-ui, sans-serif">A</text>
        </svg>
      </div>
    `,
    iconSize: [38, 50],
    iconAnchor: [19, 50],
    popupAnchor: [0, -52],
  })
}

const createDestinationLandmarkIcon = () => {
  return L.divIcon({
    className: 'custom-landmark-pin',
    html: `
      <div style="position: relative; width: 38px; height: 50px; display: flex; flex-direction: column; align-items: center; filter: drop-shadow(0 4px 10px rgba(0,0,0,0.5)); cursor: pointer;">
        <!-- Floating Pill Badge -->
        <div style="position: absolute; top: -16px; background: #9f1239; color: #fff1f2; font-size: 9px; font-weight: 900; padding: 2px 7px; border-radius: 9999px; letter-spacing: 0.5px; white-space: nowrap; border: 1.5px solid #ffffff; box-shadow: 0 2px 6px rgba(0,0,0,0.3);">
          🏁 DEST (B)
        </div>
        <!-- 3D Crimson Teardrop Pin -->
        <svg width="38" height="48" viewBox="0 0 38 48" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M19 0C8.50659 0 0 8.50659 0 19C0 29.5 14.5 43.5 18.0588 47.1765C18.5765 47.7118 19.4235 47.7118 19.9412 47.1765C23.5 43.5 38 29.5 38 19C38 8.50659 29.4934 0 19 0Z" fill="#be123c"/>
          <path d="M19 2C9.61116 2 2 9.61116 2 19C2 28 15.5 41 18.5 44.5C18.77 44.8 19.23 44.8 19.5 44.5C22.5 41 36 28 36 19C36 9.61116 28.3888 2 19 2Z" fill="#f43f5e"/>
          <circle cx="19" cy="18" r="11" fill="#ffffff" stroke="#be123c" stroke-width="2"/>
          <text x="19" y="23" font-size="12" font-weight="900" fill="#9f1239" text-anchor="middle" font-family="system-ui, sans-serif">🏁</text>
        </svg>
      </div>
    `,
    iconSize: [38, 50],
    iconAnchor: [19, 50],
    popupAnchor: [0, -52],
  })
}

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
  centerCoords?: LatLngTuple | null
  targetView?: TargetMapView | null
  navigatingUser?: {
    lat: number
    lon: number
    heading: number
    speedKmh: number
    isNavigating: boolean
    isAutoFollow?: boolean
  } | null
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

  const hasFiredRef = React.useRef(false)
  React.useEffect(() => {
    if (!hasFiredRef.current && onChange) {
      hasFiredRef.current = true
      onChange(map.getBounds(), map.getZoom())
    }
  }, [map, onChange])

  return null
}

const MapFlyToHandler: React.FC<{ targetView?: TargetMapView | null }> = ({ targetView }) => {
  const map = useMap()
  const lastKeyRef = React.useRef<string | number | null>(null)

  React.useEffect(() => {
    if (targetView && targetView.center && targetView.key !== lastKeyRef.current) {
      lastKeyRef.current = targetView.key
      map.flyTo(targetView.center, targetView.zoom, { duration: 1.5 })
    }
  }, [targetView, map])

  return null
}

const MapFollowHandler: React.FC<{ navigatingUser?: any }> = ({ navigatingUser }) => {
  const map = useMap()
  React.useEffect(() => {
    if (navigatingUser?.isNavigating && navigatingUser.lat && navigatingUser.lon && navigatingUser.isAutoFollow !== false) {
      map.setView([navigatingUser.lat, navigatingUser.lon], Math.max(map.getZoom(), 15), { animate: true })
    }
  }, [navigatingUser?.lat, navigatingUser?.lon, navigatingUser?.isNavigating, navigatingUser?.isAutoFollow, map])
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
  vehicleHistory = [],
  centerCoords,
  targetView,
  navigatingUser = null
}) => {
  const { t } = useTranslation()
  const effectiveView: TargetMapView | null = targetView || (centerCoords ? {
    center: centerCoords,
    zoom: 11,
    key: `${centerCoords[0].toFixed(3)}_${centerCoords[1].toFixed(3)}`
  } : null)

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
        <MapFlyToHandler targetView={effectiveView} />
        <MapFollowHandler navigatingUser={navigatingUser} />
        <MapClickHandler onClick={onMapClick} />
        <MapMoveHandler onChange={onViewportChange} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {roadGeoJSON && (
          <GeoJSON
            key={`roads_${roadGeoJSON.features.length}_${roadGeoJSON.features[0]?.properties?.id || 0}_${roadGeoJSON.features[roadGeoJSON.features.length - 1]?.properties?.id || 0}`}
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
          const isInTransit = v.status === 'in_transit';
          return (
            <React.Fragment key={`vehicle-grp-${v.id}`}>
              {isInTransit && (
                <CircleMarker
                  center={[v.current_lat, v.current_lon]}
                  radius={12}
                  pathOptions={{
                    fillColor: '#3b82f6',
                    color: '#3b82f6',
                    weight: 1.5,
                    fillOpacity: 0.25,
                  }}
                />
              )}
              <CircleMarker
                center={[v.current_lat, v.current_lon]}
                radius={isSelected ? 10 : 7}
                pathOptions={{
                  color: isSelected ? '#1e3a8a' : '#ffffff',
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
                  <div className="text-xs p-1 min-w-[150px]">
                    <p className="font-bold text-sm flex items-center gap-1.5">🚚 {v.vehicle_number}</p>
                    <div className="mt-1 space-y-0.5 text-[11px]">
                      <p className="text-muted-foreground">Status: <span className="font-semibold text-emerald-600 uppercase">{v.status}</span></p>
                      {v.speed_kmh !== undefined && <p className="text-muted-foreground">Speed: <span className="font-semibold text-foreground">{v.speed_kmh} km/h</span></p>}
                      {v.destination && <p className="text-muted-foreground truncate">Dest: <span className="font-semibold text-foreground">{v.destination}</span></p>}
                    </div>
                    <div className="mt-1.5 pt-1 border-t flex items-center gap-1 text-[10px] text-blue-500 font-bold tracking-wide">
                      <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-ping" />
                      <span>LIVE GPS ACTIVE</span>
                    </div>
                  </div>
                </Popup>
              </CircleMarker>
            </React.Fragment>
          )
        })}

        {/* Active Driver Navigation Marker */}
        {navigatingUser?.isNavigating && navigatingUser.lat && navigatingUser.lon && (
          <Marker
            position={[navigatingUser.lat, navigatingUser.lon]}
            icon={createDirectionalIcon(navigatingUser.heading)}
            zIndexOffset={1000}
          >
            <Popup>
              <div className="text-xs p-1">
                <p className="font-bold text-sm text-emerald-600 flex items-center gap-1">
                  <span>🧭</span> Driver Navigation (Active)
                </p>
                <div className="mt-1 space-y-0.5">
                  <p>Heading: <span className="font-semibold">{Math.round(navigatingUser.heading)}°</span></p>
                  <p>Speed: <span className="font-semibold">{Math.round(navigatingUser.speedKmh)} km/h</span></p>
                  <p className="text-[10px] text-muted-foreground pt-1 border-t">GPS Live Tracking Active</p>
                </div>
              </div>
            </Popup>
          </Marker>
        )}

        {/* Origin Landmark Pin (Snapped to start of route if route is active) */}
        {(() => {
          const effectiveOrigin: LatLngTuple | null = routeGeoJSON?.geometry?.coordinates?.length
            ? [routeGeoJSON.geometry.coordinates[0][1], routeGeoJSON.geometry.coordinates[0][0]]
            : origin

          if (!effectiveOrigin) return null

          return (
            <Marker
              position={effectiveOrigin}
              icon={createOriginLandmarkIcon()}
              zIndexOffset={10000}
            >
              <Popup>
                <div className="p-1 min-w-[160px]">
                  <p className="font-bold text-sm text-emerald-700 flex items-center gap-1.5">
                    <span>📍</span> Origin (Point A)
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">Departure Point</p>
                  <div className="mt-1.5 pt-1 border-t text-[11px] font-mono text-muted-foreground">
                    {effectiveOrigin[0].toFixed(4)}, {effectiveOrigin[1].toFixed(4)}
                  </div>
                </div>
              </Popup>
            </Marker>
          )
        })()}

        {/* Destination Landmark Pin (Snapped to end of route if route is active) */}
        {(() => {
          const coords = routeGeoJSON?.geometry?.coordinates
          const effectiveDestination: LatLngTuple | null = coords?.length
            ? [coords[coords.length - 1][1], coords[coords.length - 1][0]]
            : destination

          if (!effectiveDestination) return null

          return (
            <Marker
              position={effectiveDestination}
              icon={createDestinationLandmarkIcon()}
              zIndexOffset={10000}
            >
              <Popup>
                <div className="p-1 min-w-[160px]">
                  <p className="font-bold text-sm text-rose-700 flex items-center gap-1.5">
                    <span>🏁</span> Destination (Point B)
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">Arrival Point</p>
                  <div className="mt-1.5 pt-1 border-t text-[11px] font-mono text-muted-foreground">
                    {effectiveDestination[0].toFixed(4)}, {effectiveDestination[1].toFixed(4)}
                  </div>
                </div>
              </Popup>
            </Marker>
          )
        })()}
        {routeGeoJSON && (
          <GeoJSON 
            data={routeGeoJSON} 
            key={JSON.stringify(routeGeoJSON)}
            style={{ 
              color: routeGeoJSON.properties?.route_preference === 'safest'
                ? '#10b981'
                : (routeGeoJSON.properties?.risk_level === 'HIGH' ? '#ef4444' : 
                   routeGeoJSON.properties?.risk_level === 'MEDIUM' ? '#f59e0b' : '#3b82f6'), 
              weight: 6,
              opacity: 0.85 
            }}
          />
        )}

        {/* Highlighted Bridges Along Route */}
        {routeGeoJSON?.properties?.bridges?.map((b: any) => {
          const isPoor = b.condition === 'poor' || b.condition === 'critical'
          const isFair = b.condition === 'fair' || b.condition === 'repair_needed'
          const bridgeColor = isPoor ? '#ef4444' : isFair ? '#f59e0b' : '#10b981'
          return (
            <React.Fragment key={`route-bridge-hl-${b.id}`}>
              {/* Outer glowing ring for prominent route visibility */}
              <CircleMarker
                center={[b.latitude, b.longitude]}
                radius={isPoor ? 16 : 13}
                pathOptions={{
                  fillColor: bridgeColor,
                  color: bridgeColor,
                  weight: isPoor ? 3 : 2,
                  fillOpacity: isPoor ? 0.35 : 0.2,
                  dashArray: isPoor ? '4, 4' : undefined,
                }}
              />
              {/* Inner bridge marker */}
              <CircleMarker
                center={[b.latitude, b.longitude]}
                radius={8}
                pathOptions={{
                  fillColor: bridgeColor,
                  color: '#ffffff',
                  weight: 2.5,
                  fillOpacity: 1,
                }}
              >
                <Popup>
                  <div className="p-2 min-w-[240px] max-w-[280px] text-xs">
                    <div className="flex items-center gap-1.5 font-bold text-sm text-foreground mb-1">
                      <span>🌉</span>
                      <span className="truncate">{b.name || 'Bridge on Route'}</span>
                    </div>
                    <div className="mt-2 space-y-1.5">
                      <div className="flex justify-between items-center py-0.5 border-b">
                        <span className="text-muted-foreground">Condition:</span>
                        <span
                          className="font-bold uppercase px-2 py-0.5 rounded text-[11px]"
                          style={{
                            backgroundColor: `${bridgeColor}20`,
                            color: bridgeColor,
                          }}
                        >
                          {isPoor ? 'POOR / HIGH RISK' : isFair ? 'FAIR / CAUTION' : 'GOOD / SAFE'}
                        </span>
                      </div>

                      {/* Explicit Hazard Cause */}
                      <div className="py-1 border-b">
                        <div className="flex items-center justify-between text-[11px] font-semibold">
                          <span className="text-muted-foreground">Hazard Cause:</span>
                          <span className="font-bold flex items-center gap-1" style={{ color: bridgeColor }}>
                            {isPoor ? '🚨' : isFair ? '⚠️' : '✅'} {b.cause || (isPoor ? 'Landslide Blockade' : isFair ? 'Deck Wear & Scour' : 'Operational')}
                          </span>
                        </div>
                        {b.cause_description && (
                          <p className="text-[10px] text-muted-foreground mt-1 leading-tight bg-muted/40 p-1.5 rounded">
                            {b.cause_description}
                          </p>
                        )}
                      </div>

                      <div className="flex justify-between items-center py-0.5">
                        <span className="text-muted-foreground">Logistics Assessment:</span>
                        <span className="font-semibold text-right text-[11px]" style={{ color: bridgeColor }}>
                          {isPoor
                            ? '⚠️ Bridge Closed / Impassable'
                            : isFair
                            ? '⚠️ Speed & Load Restricted'
                            : '✅ Fully operational & safe'}
                        </span>
                      </div>
                      <div className="text-[10px] text-muted-foreground pt-1 flex justify-between border-t">
                        <span>Road ID: #{b.road_id}</span>
                        {b.last_verified && <span>Verified: {new Date(b.last_verified).toLocaleDateString()}</span>}
                      </div>
                    </div>
                  </div>
                </Popup>
              </CircleMarker>
            </React.Fragment>
          )
        })}
      </MapContainer>
      
      {/* Map Legend overlay */}
      <div className="absolute bottom-6 right-6 z-[400] bg-background/95 backdrop-blur border p-3 rounded-md shadow-sm text-xs pointer-events-none">
        <h4 className="font-semibold mb-2">Road Status</h4>
        <div className="flex flex-col gap-1.5 mb-3">
          <div className="flex items-center gap-2"><div className="w-4 h-1 bg-[#10b981] rounded-full" /> Open</div>
          <div className="flex items-center gap-2"><div className="w-4 h-1 bg-[#f59e0b] rounded-full" /> Restricted</div>
          <div className="flex items-center gap-2"><div className="w-4 h-1 bg-[#ef4444] rounded-full" /> Blocked</div>
        </div>
        
        <h4 className="font-semibold mb-2">Bridge Condition (on Route)</h4>
        <div className="flex flex-col gap-1.5 mb-3">
          <div className="flex items-center gap-2"><div className="w-2.5 h-2.5 bg-[#10b981] rounded-full border border-white" /> Good</div>
          <div className="flex items-center gap-2"><div className="w-2.5 h-2.5 bg-[#f59e0b] rounded-full border border-white" /> Fair</div>
          <div className="flex items-center gap-2"><div className="w-2.5 h-2.5 bg-[#ef4444] rounded-full border border-white" /> Poor</div>
        </div>

        <h4 className="font-semibold mb-2">Fleet (Live Tracking)</h4>
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-[#3b82f6] rounded-full border-2 border-white shadow-xs" />
            <span>Active Vehicle (Simulated GPS)</span>
          </div>
        </div>
      </div>
    </div>
  )
}
