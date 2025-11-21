import './LoadingState.css'

interface LoadingStateProps {
  message?: string
  compact?: boolean
}

export function LoadingState({ message = 'Cargando...', compact = false }: LoadingStateProps) {
  return (
    <div className={`loading-state ${compact ? 'compact' : ''}`} role="status" aria-live="polite">
      <div className="loading-spinner" aria-hidden="true">
        <div className="spinner-circle"></div>
      </div>
      <p className="loading-message">{message}</p>
    </div>
  )
}

