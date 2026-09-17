import React from 'react'
import { AlertCircle, FileWarning } from 'lucide-react'
import { ApiError } from '../../api/client'
import { useTranslation } from 'react-i18next'

type ErrorStateProps = {
  error: Error | ApiError | string | null
  onRetry?: () => void
  title?: string
}

export const ErrorState: React.FC<ErrorStateProps> = ({ error, onRetry, title }) => {
  const { t } = useTranslation()

  if (!error) return null

  let message = typeof error === 'string' ? error : error.message
  let is422 = false
  let validationDetails: any[] = []

  if (error instanceof ApiError) {
    if (error.code === 422 && Array.isArray(error.detail)) {
      is422 = true
      validationDetails = error.detail
    } else if (error.code === 401) {
      message = t('errors.unauthorized', 'Session expired. Please log in again.')
    } else if (error.code === 403) {
      message = t('errors.forbidden', 'No permission for this action.')
    }
  }

  // Network/Offline fallback mapping
  if (message.includes('Failed to fetch') || message.includes('NetworkError')) {
    message = t('errors.offline', 'Network error. Please check your connection.')
  }

  return (
    <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex flex-col gap-3">
      <div className="flex items-start gap-3">
        {is422 ? <FileWarning className="w-5 h-5 text-destructive mt-0.5 shrink-0" /> : <AlertCircle className="w-5 h-5 text-destructive mt-0.5 shrink-0" />}
        <div className="flex-1">
          <h4 className="font-semibold text-destructive">
            {title || (is422 ? t('errors.validation_title', 'Validation Error') : t('errors.default_title', 'Error'))}
          </h4>
          
          {!is422 && <p className="text-sm text-destructive/90 mt-1">{message}</p>}

          {is422 && (
            <ul className="mt-2 text-sm text-destructive/90 list-disc list-inside space-y-1">
              {validationDetails.map((detail, idx) => (
                <li key={idx}>
                  <span className="font-medium">{detail.loc?.join('.') || detail.field || 'Field'}</span>: {detail.msg || detail.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      
      {onRetry && (
        <div className="flex justify-end mt-2">
          <button 
            type="button"
            onClick={onRetry}
            className="text-xs font-medium bg-background px-3 py-1.5 rounded border shadow-sm hover:bg-muted transition-colors text-foreground"
          >
            {t('errors.retry', 'Retry')}
          </button>
        </div>
      )}
    </div>
  )
}
