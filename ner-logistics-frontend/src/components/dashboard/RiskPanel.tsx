import React, { useState, useEffect } from 'react'
import { RiskOutput, riskApi } from '../../api/risk'
import { Activity, Database, CheckCircle, ShieldAlert } from 'lucide-react'
import { RoadOut } from '../../api/infrastructure'
import { useTranslation } from 'react-i18next'
import { LoadingState } from '../shared/LoadingState'
import { ErrorState } from '../shared/ErrorState'
import { EmptyState } from '../shared/EmptyState'

interface RiskPanelProps {
  selectedRoad: RoadOut | null
}

export const RiskPanel: React.FC<RiskPanelProps> = ({ selectedRoad }) => {
  const [riskResult, setRiskResult] = useState<RiskOutput | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { t } = useTranslation()

  useEffect(() => {
    if (!selectedRoad) {
      setRiskResult(null)
      setError(null)
      return
    }

    let isMounted = true
    setLoading(true)
    setError(null)

    riskApi.predictRisk({ road_id: selectedRoad.id, rainfall_mm: 0, road_condition: selectedRoad.status === 'open' ? 'good' : 'poor', bridge_condition: 'good', recent_incidents: 0, terrain_difficulty: 0.3 })
      .then(res => {
        if (isMounted) setRiskResult(res)
      })
      .catch(err => {
        if (isMounted) setError(err.message || 'Failed to predict risk')
      })
      .finally(() => {
        if (isMounted) setLoading(false)
      })

    return () => { isMounted = false }
  }, [selectedRoad])

  if (!selectedRoad && !loading && !error && !riskResult) {
    return (
      <EmptyState 
        title={t('dashboard.risk_prediction', 'Risk Prediction')}
        description={t('dashboard.select_road_risk', 'Select a road on the map to view risk prediction.')}
        icon={<Activity className="w-8 h-8" />}
      />
    )
  }

  return (
    <div className="bg-card border rounded-lg p-4 shadow-sm flex flex-col gap-4">
      <h3 className="font-semibold text-sm flex items-center gap-2">
        <ShieldAlert className="w-4 h-4 text-primary" />
        {t('dashboard.risk_prediction', 'Risk Prediction')}
        {selectedRoad && <span className="text-xs font-normal text-muted-foreground truncate">({selectedRoad.name})</span>}
      </h3>

      {loading && <LoadingState message={t('loading.default', 'Loading...')} />}

      {error && !loading && (
        <div className="mt-2">
          <ErrorState error={error} onRetry={() => {
            setLoading(true)
            setError(null)
            riskApi.predictRisk({ road_id: selectedRoad!.id, rainfall_mm: 0, road_condition: selectedRoad!.status === 'open' ? 'good' : 'poor', bridge_condition: 'good', recent_incidents: 0, terrain_difficulty: 0.3 })
              .then(res => setRiskResult(res))
              .catch(err => setError(err.message || 'Failed to predict risk'))
              .finally(() => setLoading(false))
          }} />
        </div>
      )}

      {riskResult && !loading && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{t('dashboard.risk_score', 'Risk Score:')}</span>
            <span className="text-2xl font-bold">{riskResult.risk_score.toFixed(1)}</span>
          </div>
          
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">{t('dashboard.risk_level', 'Risk Level:')}</span>
            <span className={`text-sm font-bold px-2 py-0.5 rounded ${
              riskResult.risk_level === 'HIGH' ? 'bg-red-500/10 text-red-500' :
              riskResult.risk_level === 'MEDIUM' ? 'bg-amber-500/10 text-amber-500' : 'bg-emerald-500/10 text-emerald-500'
            }`}>
              {t(`dashboard.risk_${riskResult.risk_level?.toLowerCase()}`, riskResult.risk_level)}
            </span>
          </div>

          <div className="flex flex-col gap-1.5 mt-2">
            <span className="text-xs font-medium text-muted-foreground">{t('dashboard.factors', 'Factors:')}</span>
            <ul className="text-xs flex flex-col gap-1">
              {riskResult.factors.map((factor, i) => (
                <li key={i} className="flex items-center gap-1.5">
                  <div className="w-1 h-1 rounded-full bg-primary/50" />
                  {factor}
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-2 pt-3 border-t">
            <div className="flex flex-col gap-1.5 text-xs">
              <span className="text-muted-foreground font-semibold">{t('dashboard.prediction_source', 'Source')}</span>
              {riskResult.prediction_source === 'ml' ? (
                <span className="font-bold text-blue-500 flex items-center gap-1.5 bg-blue-500/10 px-2 py-1 rounded w-fit border border-blue-500/20">
                  <Database className="w-3.5 h-3.5" />
                  {t('dashboard.source_ml', 'AI / ML Prediction')}
                </span>
              ) : (
                <span className="font-bold text-amber-500 flex items-center gap-1.5 bg-amber-500/10 px-2 py-1 rounded w-fit border border-amber-500/20">
                  <CheckCircle className="w-3.5 h-3.5" />
                  {t('dashboard.source_tier1', 'Tier-1 Rule-Based Fallback')}
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
