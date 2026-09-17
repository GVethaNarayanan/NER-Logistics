import React, { useState, useEffect } from 'react'
import { infrastructureApi, DistrictConnectivity } from '../../api/infrastructure'
import { ApiError } from '../../api/client'
import { useTranslation } from 'react-i18next'

interface ConnectivityPanelProps {
  selectedDistrictId: number | null
}

export const ConnectivityPanel: React.FC<ConnectivityPanelProps> = ({ selectedDistrictId }) => {
  const [data, setData] = useState<DistrictConnectivity | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { t } = useTranslation()

  useEffect(() => {
    if (!selectedDistrictId) {
      setData(null)
      setError(null)
      return
    }

    let isMounted = true
    setIsLoading(true)
    setError(null)

    infrastructureApi.getDistrictConnectivity(selectedDistrictId)
      .then(res => {
        if (isMounted) setData(res)
      })
      .catch(err => {
        if (isMounted) {
          if (err instanceof ApiError) {
            setError(err.message)
          } else {
            setError('Failed to load district connectivity')
          }
        }
      })
      .finally(() => {
        if (isMounted) setIsLoading(false)
      })

    return () => {
      isMounted = false
    }
  }, [selectedDistrictId])

  // Optional: calculate a simple connectivity score based on what we have since it's not strictly returned by the DB directly
  const getConnectivityScore = (d: DistrictConnectivity) => {
    if (d.roads.total === 0 && d.bridges.total === 0) return 0
    const openRoads = d.roads.open || 0
    const goodBridges = d.bridges.good || 0
    const total = (d.roads.total || 0) + (d.bridges.total || 0)
    return total > 0 ? (openRoads + goodBridges) / total : 0
  }

  return (
    <div className="flex flex-col h-full bg-card rounded-lg border shadow-sm">
      <div className="p-4 border-b">
        <h2 className="text-lg font-semibold">{t('dashboard.connectivity_title', 'District Connectivity')}</h2>
      </div>

      <div className="p-4 flex-1 overflow-auto">
        {!selectedDistrictId ? (
          <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
            {t('dashboard.no_district_selected', 'Select a district to view infrastructure statistics.')}
          </div>
        ) : isLoading ? (
          <div className="flex items-center justify-center h-full text-sm text-muted-foreground animate-pulse">
            Loading connectivity data...
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-full text-sm text-destructive text-center p-4 bg-destructive/10 rounded-md">
            {error}
          </div>
        ) : !data || (data.roads.total === 0 && data.bridges.total === 0) ? (
          <div className="flex items-center justify-center h-full text-sm text-muted-foreground text-center">
            No infrastructure data available for this district.
          </div>
        ) : (
          <div className="space-y-6">
            <div>
              <h3 className="text-sm font-medium text-muted-foreground mb-3">{t('dashboard.road_status', 'Road Overview')}</h3>
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-muted/50 p-3 rounded-md">
                  <div className="text-2xl font-bold">{data.roads.total}</div>
                  <div className="text-xs text-muted-foreground mt-1">Total Roads</div>
                </div>
                <div className="bg-emerald-500/10 p-3 rounded-md">
                  <div className="text-2xl font-bold text-emerald-600">{data.roads.open}</div>
                  <div className="text-xs text-emerald-600/80 mt-1">{t('dashboard.open', 'Open')}</div>
                </div>
                <div className="bg-amber-500/10 p-3 rounded-md">
                  <div className="text-2xl font-bold text-amber-600">{data.roads.restricted}</div>
                  <div className="text-xs text-amber-600/80 mt-1">{t('dashboard.restricted', 'Restricted')}</div>
                </div>
                <div className="bg-red-500/10 p-3 rounded-md">
                  <div className="text-2xl font-bold text-red-600">{data.roads.blocked}</div>
                  <div className="text-xs text-red-600/80 mt-1">{t('dashboard.blocked', 'Blocked')}</div>
                </div>
              </div>
            </div>

            <div>
              <h3 className="text-sm font-medium text-muted-foreground mb-3">{t('dashboard.bridge_condition', 'Bridge Condition')}</h3>
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-muted/50 p-3 rounded-md">
                  <div className="text-2xl font-bold">{data.bridges.total}</div>
                  <div className="text-xs text-muted-foreground mt-1">Total Bridges</div>
                </div>
                <div className="bg-emerald-500/10 p-3 rounded-md">
                  <div className="text-2xl font-bold text-emerald-600">{data.bridges.good}</div>
                  <div className="text-xs text-emerald-600/80 mt-1">{t('dashboard.good', 'Good')}</div>
                </div>
                <div className="bg-amber-500/10 p-3 rounded-md">
                  <div className="text-2xl font-bold text-amber-600">{data.bridges.fair}</div>
                  <div className="text-xs text-amber-600/80 mt-1">{t('dashboard.fair', 'Fair')}</div>
                </div>
                <div className="bg-red-500/10 p-3 rounded-md">
                  <div className="text-2xl font-bold text-red-600">{data.bridges.poor}</div>
                  <div className="text-xs text-red-600/80 mt-1">{t('dashboard.poor', 'Poor')}</div>
                </div>
              </div>
            </div>
            
            <div className="pt-4 border-t">
               <div className="flex justify-between items-center bg-primary/5 p-3 rounded-md border border-primary/10">
                 <span className="text-sm font-medium">Connectivity Score</span>
                 <span className="text-lg font-bold text-primary">{(getConnectivityScore(data) * 100).toFixed(1)}%</span>
               </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
