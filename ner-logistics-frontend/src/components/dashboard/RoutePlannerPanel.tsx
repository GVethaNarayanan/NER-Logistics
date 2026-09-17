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
}

export const RoutePlannerPanel: React.FC<RoutePlannerPanelProps> = ({
  origin,
  destination,
  selectingMode,
  setSelectingMode,
  onCalculateRoute,
  routeLoading,
  routeError,
  routeResult
}) => {
  const [preference, setPreference] = useState<'shortest' | 'safest'>('shortest')
  const { t } = useTranslation()

  return (
    <div className="bg-card border rounded-lg p-4 shadow-sm flex flex-col gap-4">
      <h3 className="font-semibold text-sm flex items-center gap-2">
        <Navigation className="w-4 h-4 text-primary" />
        {t('dashboard.route_planner', 'Route Planner')}
      </h3>

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
        </div>
      )}
    </div>
  )
}
