import { isTimeoutError, getErrorMessage, isNetworkError } from '../../api/hooks'
import './ErrorState.css'

interface ErrorStateProps {
  error: unknown
  title?: string
  onRetry?: () => void
  showRetry?: boolean
}

export function ErrorState({ error, title = 'Error al cargar datos', onRetry, showRetry = true }: ErrorStateProps) {
  const isTimeout = isTimeoutError(error)
  const isNetwork = isNetworkError(error)
  const errorMessage = getErrorMessage(error)

  return (
    <div className="error-state" role="alert" aria-live="assertive">
      <div className="error-state-content">
        <div className="error-icon">
          {isTimeout ? '⏱️' : isNetwork ? '🌐' : '❌'}
        </div>
        <h3 className="error-title">{title}</h3>
        {isTimeout ? (
          <div className="error-message timeout-error">
            <p><strong>El backend está ocupado procesando la solicitud.</strong></p>
            <p>Por favor, intenta nuevamente en unos momentos.</p>
            {showRetry && onRetry && (
              <button 
                type="button" 
                className="error-retry-button"
                onClick={onRetry}
              >
                🔄 Reintentar
              </button>
            )}
          </div>
        ) : isNetwork ? (
          <div className="error-message network-error">
            <p><strong>No se pudo conectar con el backend.</strong></p>
            <p>Verifica tu conexión a internet e intenta nuevamente.</p>
            {showRetry && onRetry && (
              <button 
                type="button" 
                className="error-retry-button"
                onClick={onRetry}
              >
                🔄 Reintentar
              </button>
            )}
          </div>
        ) : (
          <div className="error-message generic-error">
            <p>{errorMessage}</p>
            {showRetry && onRetry && (
              <button 
                type="button" 
                className="error-retry-button"
                onClick={onRetry}
              >
                🔄 Reintentar
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

