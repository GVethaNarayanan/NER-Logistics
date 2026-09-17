import React from 'react'
import { Loader2 } from 'lucide-react'

type LoadingStateProps = {
  message?: string
  fullScreen?: boolean
  overlay?: boolean
}

export const LoadingState: React.FC<LoadingStateProps> = ({ 
  message = 'Loading...', 
  fullScreen = false,
  overlay = false
}) => {
  const content = (
    <div className="flex flex-col items-center justify-center gap-2 p-8 text-muted-foreground animate-in fade-in duration-500">
      <Loader2 className="w-8 h-8 animate-spin text-primary" />
      <p className="text-sm font-medium">{message}</p>
    </div>
  )

  if (fullScreen) {
    return (
      <div className="flex-1 min-h-[50vh] flex items-center justify-center">
        {content}
      </div>
    )
  }

  if (overlay) {
    return (
      <div className="absolute inset-0 z-50 bg-background/50 backdrop-blur-sm flex items-center justify-center rounded-inherit">
        {content}
      </div>
    )
  }

  return content
}
