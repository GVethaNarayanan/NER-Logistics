import React, { useState, useEffect, useCallback } from 'react'
import { AlertCircle, CheckCircle, Clock, ShieldAlert, Filter, Plus, RefreshCw } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { alertApi, AlertOut, AlertCreate } from '../api/alerts'
import { useTranslation } from 'react-i18next'
import { LoadingState } from '../components/shared/LoadingState'
import { ErrorState } from '../components/shared/ErrorState'
import { EmptyState } from '../components/shared/EmptyState'

export const getAlertMessage = (alert: AlertOut, currentLang: string): string => {
  if (currentLang === 'as') {
    return alert.message_local || alert.message_en
  }
  return alert.message_en
}

export const Alerts: React.FC = () => {
  const { role } = useAuth()
  const isAdmin = role === 'admin'
  const { t, i18n } = useTranslation()
  
  const [alerts, setAlerts] = useState<AlertOut[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  
  // Pagination
  const [skip, setSkip] = useState(0)
  const limit = 20
  
  // Filters
  const [filterStatus, setFilterStatus] = useState<string>('')
  const [filterSeverity, setFilterSeverity] = useState<string>('')
  
  // Manual Create Modal
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  
  // Create Form State
  const [formType, setFormType] = useState('general')
  const [formSeverity, setFormSeverity] = useState('medium')
  const [formMessageEn, setFormMessageEn] = useState('')
  const [formMessageLocal, setFormMessageLocal] = useState('')
  const [formRoadId, setFormRoadId] = useState('')
  const [formBridgeId, setFormBridgeId] = useState('')

  const fetchAlerts = useCallback(async (isManualRefresh = false) => {
    if (isManualRefresh) setLoading(true)
    setError(null)
    try {
      const res = await alertApi.getAlerts({
        status: filterStatus || undefined,
        severity: filterSeverity || undefined,
        skip,
        limit
      })
      setAlerts(res.items)
      setTotal(res.total)
    } catch (err: any) {
      setError(err.message || 'Failed to fetch alerts')
    } finally {
      setLoading(false)
    }
  }, [filterStatus, filterSeverity, skip, limit])

  // Polling Effect
  useEffect(() => {
    fetchAlerts()
    const interval = setInterval(() => {
      fetchAlerts(false)
    }, 30000)
    return () => clearInterval(interval)
  }, [fetchAlerts])

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!isAdmin) return
    
    setCreating(true)
    setCreateError(null)
    
    try {
      const payload: AlertCreate = {
        alert_type: formType,
        severity: formSeverity,
        message_en: formMessageEn,
        message_local: formMessageLocal || null,
        language: 'en',
        road_id: formRoadId ? parseInt(formRoadId) : null,
        bridge_id: formBridgeId ? parseInt(formBridgeId) : null
      }
      
      await alertApi.createAlert(payload)
      setShowCreateModal(false)
      // Reset form
      setFormType('general')
      setFormSeverity('medium')
      setFormMessageEn('')
      setFormMessageLocal('')
      setFormRoadId('')
      setFormBridgeId('')
      
      // Refresh list
      fetchAlerts(true)
    } catch (err: any) {
      setCreateError(err.message || 'Failed to create alert')
    } finally {
      setCreating(false)
    }
  }

  const getSeverityColor = (severity: string) => {
    switch (severity?.toLowerCase()) {
      case 'high': return 'bg-destructive/10 text-destructive border-destructive/20'
      case 'medium': return 'bg-orange-500/10 text-orange-600 border-orange-500/20'
      case 'low': return 'bg-blue-500/10 text-blue-600 border-blue-500/20'
      default: return 'bg-secondary text-secondary-foreground border-border'
    }
  }

  return (
    <div className="container mx-auto p-4 md:p-8 flex flex-col gap-6">
      
      {/* Header Area */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3">
            <AlertCircle className="w-8 h-8 text-destructive" />
            {t('alerts.title', 'System Alerts')}
          </h1>
          <p className="text-muted-foreground mt-2">{t('alerts.subtitle', 'Active and historical alerts from the logistics network.')}</p>
        </div>
        
        <div className="flex gap-2">
          <button 
            onClick={() => fetchAlerts(true)} 
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-secondary text-secondary-foreground rounded-md hover:bg-secondary/80 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            {t('alerts.refresh', 'Refresh')}
          </button>
          
          {isAdmin && (
            <button 
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
            >
              <Plus className="w-4 h-4" />
              {t('alerts.new_alert', 'New Alert')}
            </button>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="bg-card border rounded-lg p-4 flex flex-wrap gap-4 items-end shadow-sm">
        <div className="flex flex-col gap-1.5 flex-1 min-w-[150px]">
          <label className="text-sm font-medium flex items-center gap-1.5 text-muted-foreground">
            <Filter className="w-3.5 h-3.5" /> {t('alerts.filter_status', 'Status')}
          </label>
          <select 
            value={filterStatus} 
            onChange={e => { setSkip(0); setFilterStatus(e.target.value) }}
            className="w-full bg-background border rounded px-3 py-2 text-sm focus:ring-1 focus:ring-primary"
          >
            <option value="">{t('alerts.all_statuses', 'All Statuses')}</option>
            <option value="active">{t('alerts.status_active', 'Active')}</option>
            <option value="resolved">{t('alerts.status_resolved', 'Resolved')}</option>
          </select>
        </div>
        <div className="flex flex-col gap-1.5 flex-1 min-w-[150px]">
          <label className="text-sm font-medium flex items-center gap-1.5 text-muted-foreground">
            <ShieldAlert className="w-3.5 h-3.5" /> {t('alerts.filter_severity', 'Severity')}
          </label>
          <select 
            value={filterSeverity} 
            onChange={e => { setSkip(0); setFilterSeverity(e.target.value) }}
            className="w-full bg-background border rounded px-3 py-2 text-sm focus:ring-1 focus:ring-primary"
          >
            <option value="">{t('alerts.all_severities', 'All Severities')}</option>
            <option value="high">{t('alerts.severity_high', 'High')}</option>
            <option value="medium">{t('alerts.severity_medium', 'Medium')}</option>
            <option value="low">{t('alerts.severity_low', 'Low')}</option>
          </select>
        </div>
      </div>

      {/* Error State */}
      {error && <ErrorState error={error} onRetry={() => fetchAlerts(true)} />}

      {/* Alerts List */}
      <div className="flex flex-col gap-4">
        {loading && alerts.length === 0 ? (
          <LoadingState message={t('loading.default', 'Loading...')} />
        ) : alerts.length === 0 && !error ? (
          <EmptyState 
            title={t('alerts.empty_title', 'No Alerts Found')} 
            description={t('alerts.no_alerts', 'No alerts found matching your criteria.')} 
            icon={<CheckCircle className="w-8 h-8" />} 
          />
        ) : (
          alerts.map(alert => {
            const isActive = alert.status === 'active'
            const displayMsg = getAlertMessage(alert, i18n.language)
            const severityKey = `alerts.severity_${alert.severity?.toLowerCase()}`
            const translatedSeverity = t(severityKey, alert.severity || 'UNKNOWN')
            
            return (
              <div 
                key={alert.id}
                className={`
                  relative overflow-hidden rounded-lg border p-5 transition-all shadow-sm
                  ${isActive ? 'bg-card border-border/80' : 'bg-muted/30 border-muted opacity-75'}
                `}
              >
                {/* Visual Indicator strip on left */}
                <div className={`absolute left-0 top-0 bottom-0 w-1 ${isActive ? (alert.severity === 'high' ? 'bg-destructive' : alert.severity === 'medium' ? 'bg-orange-500' : 'bg-blue-500') : 'bg-muted-foreground/30'}`} />
                
                <div className="flex flex-col md:flex-row gap-4 justify-between items-start">
                  
                  <div className="flex flex-col gap-2 flex-1">
                    <div className="flex flex-wrap items-center gap-2 mb-1">
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full uppercase tracking-wide border ${getSeverityColor(alert.severity || '')}`}>
                        {translatedSeverity}
                      </span>
                      
                      {!isActive && (
                        <span className="text-xs font-medium px-2 py-0.5 rounded bg-muted text-muted-foreground border flex items-center gap-1">
                          <CheckCircle className="w-3 h-3" /> {t('alerts.status_resolved', 'Resolved')}
                        </span>
                      )}
                      
                      <span className="text-xs font-medium px-2 py-0.5 rounded bg-secondary text-secondary-foreground border">
                        {t(`alerts.type_${alert.alert_type?.toLowerCase()}`, alert.alert_type)}
                      </span>
                      
                      {alert.road_id && (
                        <span className="text-xs font-medium px-2 py-0.5 rounded border border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-400">
                          Road #{alert.road_id}
                        </span>
                      )}
                      {alert.bridge_id && (
                        <span className="text-xs font-medium px-2 py-0.5 rounded border border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-400">
                          Bridge #{alert.bridge_id}
                        </span>
                      )}
                    </div>
                    <div className={`text-base ${isActive ? 'font-medium text-foreground' : 'text-muted-foreground line-through decoration-muted-foreground/30'}`}>
                      {displayMsg}
                    </div>
                  </div>
                  
                  <div className="flex flex-col items-end gap-1 text-xs text-muted-foreground shrink-0 mt-2 md:mt-0">
                    <div className="flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5" />
                      <span>{new Date(alert.created_at).toLocaleString()}</span>
                    </div>
                    {alert.resolved_at && (
                      <div className="flex items-center gap-1.5 text-emerald-600/70">
                        <CheckCircle className="w-3.5 h-3.5" />
                        <span>{new Date(alert.resolved_at).toLocaleString()}</span>
                      </div>
                    )}
                    <div className="mt-1 font-mono text-[10px] opacity-50">
                      ID: {alert.id}
                    </div>
                  </div>
                  
                </div>
              </div>
            )
          })
        )}
      </div>
      
      {/* Pagination Controls */}
      {total > limit && (
        <div className="flex justify-between items-center bg-card p-4 rounded-lg border shadow-sm">
          <p className="text-sm text-muted-foreground">
            Showing <span className="font-medium text-foreground">{skip + 1}</span> to <span className="font-medium text-foreground">{Math.min(skip + limit, total)}</span> of <span className="font-medium text-foreground">{total}</span>
          </p>
          <div className="flex gap-2">
            <button 
              onClick={() => setSkip(Math.max(0, skip - limit))}
              disabled={skip === 0}
              className="px-3 py-1.5 border rounded text-sm font-medium hover:bg-secondary disabled:opacity-50"
            >
              Previous
            </button>
            <button 
              onClick={() => setSkip(skip + limit)}
              disabled={skip + limit >= total}
              className="px-3 py-1.5 border rounded text-sm font-medium hover:bg-secondary disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Admin Manual Create Modal */}
      {showCreateModal && isAdmin && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-card w-full max-w-lg border rounded-xl shadow-xl overflow-hidden flex flex-col">
            <div className="p-6 border-b flex justify-between items-center bg-muted/30">
              <h2 className="text-xl font-bold flex items-center gap-2">
                <Plus className="w-5 h-5 text-primary" />
                {t('alerts.create_title', 'Create Manual Alert')}
              </h2>
              <button 
                onClick={() => setShowCreateModal(false)}
                className="text-muted-foreground hover:text-foreground text-2xl leading-none"
              >
                &times;
              </button>
            </div>
            
            <form onSubmit={handleCreateSubmit} className="p-6 flex flex-col gap-4">
              
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="formType" className="text-sm font-medium">{t('alerts.type', 'Type')} <span className="text-destructive">*</span></label>
                  <select id="formType" value={formType} onChange={e => setFormType(e.target.value)} className="bg-background border rounded px-3 py-2" required>
                    <option value="general">{t('alerts.type_general', 'General')}</option>
                    <option value="weather">{t('alerts.type_weather', 'Weather')}</option>
                    <option value="infrastructure">{t('alerts.type_infrastructure', 'Infrastructure')}</option>
                    <option value="security">{t('alerts.type_security', 'Security')}</option>
                  </select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="formSeverity" className="text-sm font-medium">{t('alerts.filter_severity', 'Severity')} <span className="text-destructive">*</span></label>
                  <select id="formSeverity" value={formSeverity} onChange={e => setFormSeverity(e.target.value)} className="bg-background border rounded px-3 py-2" required>
                    <option value="low">{t('alerts.severity_low', 'Low')}</option>
                    <option value="medium">{t('alerts.severity_medium', 'Medium')}</option>
                    <option value="high">{t('alerts.severity_high', 'High')}</option>
                  </select>
                </div>
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="formMessageEn" className="text-sm font-medium">{t('alerts.message_en', 'Message (English)')} <span className="text-destructive">*</span></label>
                <textarea 
                  id="formMessageEn"
                  value={formMessageEn} 
                  onChange={e => setFormMessageEn(e.target.value)} 
                  className="bg-background border rounded px-3 py-2 min-h-[80px]"
                  placeholder="E.g., Severe flooding expected on NH-37."
                  required
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-medium">{t('alerts.message_local', 'Message (Local - Optional)')}</label>
                <textarea 
                  value={formMessageLocal} 
                  onChange={e => setFormMessageLocal(e.target.value)} 
                  className="bg-background border rounded px-3 py-2 min-h-[80px]"
                  placeholder="Local translation if available."
                />
              </div>
              
              <div className="grid grid-cols-2 gap-4">
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-muted-foreground">{t('alerts.road_id', 'Road ID (Optional)')}</label>
                  <input 
                    type="number"
                    value={formRoadId} 
                    onChange={e => setFormRoadId(e.target.value)} 
                    className="bg-background border rounded px-3 py-2"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium text-muted-foreground">{t('alerts.bridge_id', 'Bridge ID (Optional)')}</label>
                  <input 
                    type="number" 
                    value={formBridgeId} 
                    onChange={e => setFormBridgeId(e.target.value)} 
                    className="bg-background border rounded px-3 py-2"
                  />
                </div>
              </div>

              {createError && (
                <div className="mt-4">
                  <ErrorState error={createError} />
                </div>
              )}

              <div className="flex justify-end gap-3 mt-4 pt-4 border-t">
                <button 
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-secondary text-secondary-foreground rounded font-medium hover:bg-secondary/80"
                  disabled={creating}
                >
                  Cancel
                </button>
                <button 
                  type="submit"
                  disabled={creating || !formMessageEn}
                  className="px-4 py-2 bg-primary text-primary-foreground rounded font-medium hover:bg-primary/90 flex items-center gap-2 disabled:opacity-50"
                >
                  {creating && <RefreshCw className="w-4 h-4 animate-spin" />}
                  {creating ? t('alerts.creating', 'Creating...') : t('alerts.create', 'Create Alert')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
