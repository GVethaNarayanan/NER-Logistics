import React, { useState } from 'react'
import { LatLngTuple } from 'leaflet'
import { RouteResponse } from '../../api/routing'
import { MapPin, Navigation, Info } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { ErrorState } from '../shared/ErrorState'

interface RoutePlannerPanelProps {
  origin: LatLngTuple | null
  destination: LatLngTuple | null
  selectingMode: 'origin' | 'destination' | null
  setSelectingMode: (mode: 'origin' | 'destination' | null) => void
  onCalculateRoute: (preference: 'shortest' | 'safest') => void
  routeLoading: boolean
  routeError: string | null
  routeResult: RouteResponse | null
  onStartNavigation?: () => void
  isNavigating?: boolean
  onSetRoutePresets?: (orig: LatLngTuple, dest: LatLngTuple) => void
}

const PRESET_CORRIDORS: Array<{ name: string; origin: LatLngTuple; dest: LatLngTuple; label: string }> = [
  { name: 'Guwahati ➔ Itanagar', origin: [26.1824, 91.7539], dest: [27.0970, 93.6166], label: 'GHY ➔ ITA (Arunachal)' },
  { name: 'Shillong ➔ Silchar', origin: [25.5788, 91.8933], dest: [24.8333, 92.7789], label: 'SHL ➔ SIL (Assam/Meghalaya)' },
  { name: 'Tezpur ➔ Bomdila', origin: [26.6528, 92.7926], dest: [27.2645, 92.4229], label: 'TEZ ➔ BOM (Hills)' },
]

export const RoutePlannerPanel: React.FC<RoutePlannerPanelProps> = ({
  origin,
  destination,
  selectingMode,
  setSelectingMode,
  onCalculateRoute,
  routeLoading,
  routeError,
  routeResult,
  onStartNavigation,
  isNavigating = false,
  onSetRoutePresets
}) => {
  const [preference, setPreference] = useState<'shortest' | 'safest'>('shortest')
  const { t } = useTranslation()

  return (
    <div className="bg-card border rounded-lg p-4 shadow-sm flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm flex items-center gap-2">
          <Navigation className="w-4 h-4 text-primary" />
          {t('dashboard.route_planner', 'Route Planner')}
        </h3>
        <span className="text-[10px] font-medium bg-primary/10 text-primary px-2 py-0.5 rounded-full">
          Live GPS
        </span>
      </div>

      {/* Quick Corridor Selection */}
      {onSetRoutePresets && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
            ⚡ Quick Corridors
          </span>
          <div className="flex flex-wrap gap-1.5">
            {PRESET_CORRIDORS.map((c) => (
              <button
                key={c.name}
                type="button"
                onClick={() => onSetRoutePresets(c.origin, c.dest)}
                className="text-[11px] font-medium py-1 px-2.5 rounded-md border bg-muted/40 hover:bg-primary hover:text-primary-foreground hover:border-primary transition-all text-left shadow-xs"
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-col gap-2">
        <button 
          onClick={() => setSelectingMode('origin')}
          className={`flex items-center gap-2 p-2 border rounded text-left text-sm transition-colors ${selectingMode === 'origin' ? 'ring-2 ring-primary border-primary' : 'hover:bg-muted/50'}`}
        >
          <MapPin className="w-4 h-4 text-blue-500" />
          <div className="flex flex-col">
            <span className="font-medium">{t('dashboard.origin', 'Origin')}</span>
            <span className="text-xs text-muted-foreground">
              {origin ? `${origin[0].toFixed(4)}, ${origin[1].toFixed(4)}` : t('dashboard.click_map', 'Click map to select')}
            </span>
          </div>
        </button>

        <button 
          onClick={() => setSelectingMode('destination')}
          className={`flex items-center gap-2 p-2 border rounded text-left text-sm transition-colors ${selectingMode === 'destination' ? 'ring-2 ring-primary border-primary' : 'hover:bg-muted/50'}`}
        >
          <MapPin className="w-4 h-4 text-pink-500" />
          <div className="flex flex-col">
            <span className="font-medium">{t('dashboard.destination', 'Destination')}</span>
            <span className="text-xs text-muted-foreground">
              {destination ? `${destination[0].toFixed(4)}, ${destination[1].toFixed(4)}` : t('dashboard.click_map', 'Click map to select')}
            </span>
          </div>
        </button>
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium">{t('dashboard.route_preference', 'Route Preference')}</span>
        <div className="flex gap-2">
          <button 
            className={`flex-1 py-1.5 px-3 text-xs rounded border transition-colors ${preference === 'shortest' ? 'bg-primary text-primary-foreground border-primary' : 'bg-transparent hover:bg-muted'}`}
            onClick={() => setPreference('shortest')}
          >
            {t('dashboard.shortest', 'Shortest')}
          </button>
          <button 
            className={`flex-1 py-1.5 px-3 text-xs rounded border transition-colors ${preference === 'safest' ? 'bg-primary text-primary-foreground border-primary' : 'bg-transparent hover:bg-muted'}`}
            onClick={() => setPreference('safest')}
          >
            {t('dashboard.safest', 'Lowest available route risk (Safest)')}
          </button>
        </div>
      </div>

      <button
        onClick={() => onCalculateRoute(preference)}
        disabled={!origin || !destination || routeLoading}
        className="w-full bg-primary text-primary-foreground py-2 rounded text-sm font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
      >
        {routeLoading ? (
          <>
            <div className="w-4 h-4 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin" />
            {t('dashboard.calculating', 'Calculating...')}
          </>
        ) : t('dashboard.calculate_route', 'Calculate Route')}
      </button>

      {routeError && (
        <div className="mt-2">
          <ErrorState error={routeError} />
        </div>
      )}

      {routeResult && (
        <div className="border rounded bg-muted/30 p-3 flex flex-col gap-2">
          <h4 className="text-sm font-semibold flex items-center gap-1.5">
            <Info className="w-4 h-4" />
            {t('dashboard.route_result', 'Route Result')}
          </h4>
          <div className="grid grid-cols-2 gap-y-2 text-xs">
            <span className="text-muted-foreground">{t('dashboard.distance', 'Distance:')}</span>
            <span className="font-medium">{((routeResult.properties as any).total_distance_km)?.toFixed(2)} km</span>
            
            <span className="text-muted-foreground">Est. Duration:</span>
            <span className="font-medium">{((routeResult.properties as any).estimated_duration_minutes)?.toFixed(0)} min</span>
            
            <span className="text-muted-foreground">{t('dashboard.avg_risk', 'Average risk:')}</span>
            <span className="font-medium">{((routeResult.properties as any).average_risk_score)?.toFixed(1)}</span>
            
            <span className="text-muted-foreground">{t('dashboard.max_risk', 'Maximum risk:')}</span>
            <span className="font-medium">{((routeResult.properties as any).max_risk_score)?.toFixed(1)}</span>
            
            <span className="text-muted-foreground">{t('dashboard.risk_level', 'Risk level:')}</span>
            <span className={`font-bold ${
              (routeResult.properties as any).risk_level === 'HIGH' ? 'text-red-500' :
              (routeResult.properties as any).risk_level === 'MEDIUM' ? 'text-amber-500' : 'text-emerald-500'
            }`}>
              {t(`dashboard.risk_${(routeResult.properties as any).risk_level?.toLowerCase()}`, (routeResult.properties as any).risk_level) as string}
            </span>
          </div>

          {/* Start Navigation CTA */}
          {onStartNavigation && (
            <button
              onClick={onStartNavigation}
              className={`w-full mt-1 py-2.5 px-3 rounded-lg font-bold text-xs shadow-md flex items-center justify-center gap-2 transition-all active:scale-[0.98] ${
                isNavigating
                  ? 'bg-amber-600 hover:bg-amber-700 text-white animate-pulse'
                  : 'bg-emerald-600 hover:bg-emerald-700 text-white'
              }`}
            >
              <Navigation className="w-4 h-4 fill-white" />
              <span>{isNavigating ? '● Active Navigation Running (Click to Focus)' : 'Start Live Navigation & Direction'}</span>
            </button>
          )}

          {/* Bridges on Selected Route */}
          <div className="mt-2 pt-2 border-t flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold flex items-center gap-1.5 text-foreground">
                <span>🌉</span> Bridges on Route:
              </span>
              <span className="text-xs font-bold px-2 py-0.5 bg-muted rounded-full">
                {(routeResult.properties as any).bridge_count || 0}
              </span>
            </div>

            {((routeResult.properties as any).bridge_count > 0) ? (
              <>
                {/* Condition badges breakdown */}
                <div className="flex gap-1.5 text-[11px]">
                  <span className="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-600 font-semibold border border-emerald-500/30">
                    ✓ {(routeResult.properties as any).bridges_good || 0} Good
                  </span>
                  <span className="px-2 py-0.5 rounded bg-amber-500/15 text-amber-600 font-semibold border border-amber-500/30">
                    ! {(routeResult.properties as any).bridges_fair || 0} Fair
                  </span>
                  <span className="px-2 py-0.5 rounded bg-red-500/15 text-red-600 font-semibold border border-red-500/30">
                    ✕ {(routeResult.properties as any).bridges_poor || 0} Poor
                  </span>
                </div>

                {/* High-risk warning if any poor/critical bridges exist */}
                {((routeResult.properties as any).bridges_poor > 0) && (
                  <div className="bg-red-500/10 border border-red-500/30 text-red-600 p-2 rounded text-xs flex items-start gap-1.5">
                    <span className="text-sm">⚠️</span>
                    <div>
                      <strong>Bridge Alert:</strong> {(routeResult.properties as any).bridges_poor} bridge(s) in <strong>POOR</strong> condition along this corridor!
                      {(routeResult.properties as any).poor_causes?.length > 0 && (
                        <div className="mt-1 font-semibold text-[11px] text-red-700 dark:text-red-400">
                          🚨 Hazard Cause: {(routeResult.properties as any).poor_causes.join(', ')}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Clear & Safe Route Notice for Safest Route */}
                {((routeResult.properties as any).route_preference === 'safest' && (routeResult.properties as any).bridges_poor === 0) && (
                  <div className="bg-emerald-500/10 border border-emerald-500/30 text-emerald-700 dark:text-emerald-400 p-2 rounded text-xs flex items-start gap-1.5">
                    <span className="text-sm">✅</span>
                    <div>
                      <strong>Clear & Safe Route:</strong> All hazardous bridges and landslide zones bypassed. Safe corridor verified.
                    </div>
                  </div>
                )}

                {/* Bridges item list */}
                <div className="max-h-48 overflow-y-auto space-y-1.5 pr-0.5 mt-1">
                  {(routeResult.properties as any).bridges?.map((b: any, idx: number) => {
                    const isPoor = b.condition === 'poor' || b.condition === 'critical'
                    const isFair = b.condition === 'fair' || b.condition === 'repair_needed'
                    const badgeClass = isPoor
                      ? 'bg-red-500/15 text-red-600 border-red-500/30'
                      : isFair
                      ? 'bg-amber-500/15 text-amber-600 border-amber-500/30'
                      : 'bg-emerald-500/15 text-emerald-600 border-emerald-500/30'

                    return (
                      <div
                        key={`bridge-item-${b.id || idx}`}
                        className="text-[11px] p-2 rounded bg-card border flex flex-col gap-1 shadow-xs"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate max-w-[170px] font-medium" title={b.name}>
                            {b.name}
                          </span>
                          <span className={`px-1.5 py-0.5 rounded font-bold uppercase text-[9px] border ${badgeClass}`}>
                            {isPoor ? 'POOR' : isFair ? 'FAIR' : 'GOOD'}
                          </span>
                        </div>
                        {b.cause && (
                          <div className="flex items-center justify-between text-[10px] text-muted-foreground pt-1 border-t border-border/40">
                            <span className="font-semibold flex items-center gap-1" style={{ color: isPoor ? '#ef4444' : isFair ? '#f59e0b' : '#10b981' }}>
                              <span>{isPoor ? '🚨 Cause:' : isFair ? '⚠️ Issue:' : 'Status:'}</span>
                              <span className="truncate max-w-[190px]">{b.cause}</span>
                            </span>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </>
            ) : (
              <p className="text-[11px] text-muted-foreground italic">
                No major river bridge crossings on this specific path.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
