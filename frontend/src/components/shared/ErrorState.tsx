import { isTimeoutError, getErrorMessage, isNetworkError, isBackendDown, isEmptyDatabase } from '../../api/hooks'
import './ErrorState.css'

interface ErrorStateProps {
  error: unknown
  title?: string
  onRetry?: () => void
  showRetry?: boolean
}

export function ErrorState({ error, title = 'Error al cargar datos', onRetry, showRetry = true }: ErrorStateProps) {
  const isTimeout = isTimeoutError(error)
  const backendDown = isBackendDown(error)
  const emptyDb = isEmptyDatabase(error)
  const isNetwork = isNetworkError(error)
  const errorMessage = getErrorMessage(error)

  return (
    <div className="error-state" role="alert" aria-live="assertive">
      <div className="error-state-content">
        <div className="error-icon">
          {isTimeout ? '⏱️' : backendDown ? '🔴' : emptyDb ? '📭' : isNetwork ? '🌐' : '❌'}
        </div>
        <h3 className="error-title">{title}</h3>
        {isTimeout ? (
          <div className="error-message timeout-error">
            <p><strong>⏱️ Tiempo de espera excedido (25s)</strong></p>
            <p>El backend puede estar ejecutando el pipeline inicial o ingiriendo datos.</p>
            <div className="error-instructions" style={{ marginTop: '1rem' }}>
              <p><strong>Pasos para solucionar:</strong></p>
              <ol>
                <li>Espera a que termine el pipeline (puede tardar varios minutos)</li>
                <li>Verifica en los logs del backend que el pipeline haya finalizado</li>
                <li>Después de que termine, recarga esta página (F5 o Ctrl+R)</li>
                <li>Si el timeout persiste después de que el pipeline termine, verifica:</li>
                <li style={{ marginLeft: '1.5rem', listStyle: 'none' }}>
                  <ul style={{ marginTop: '0.5rem' }}>
                    <li>El backend está corriendo y accesible</li>
                    <li>La URL del backend está correcta (verifica en DevTools &gt; Network)</li>
                    <li>Si usas otro host/puerto, configura <code>VITE_API_BASE_URL</code> en <code>frontend/.env</code></li>
                    <li>Reinicia Vite después de cambiar <code>.env</code>: <code>pnpm run dev</code></li>
                  </ul>
                </li>
              </ol>
            </div>
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
        ) : backendDown ? (
          <div className="error-message backend-down-error">
            <p><strong>Backend no disponible</strong></p>
            <p>{errorMessage}</p>
            <div className="error-instructions">
              <p><strong>Pasos para solucionar:</strong></p>
              <ol>
                <li>Verifica que el backend esté corriendo en la URL configurada</li>
                <li>Arranca el backend en <code>backend/</code> ejecutando:</li>
                <li className="code-block">./start-dev.ps1</li>
                <li>o</li>
                <li className="code-block">uvicorn app.main:app --reload --port 8000</li>
                <li>Espera a ver el log de "Application startup complete"</li>
                <li>Si el backend está en otro host/puerto, configura <code>VITE_API_BASE_URL</code> en <code>frontend/.env</code></li>
                <li className="code-block">VITE_API_BASE_URL=http://127.0.0.1:8000</li>
                <li>Después de cambiar <code>.env</code>, reinicia Vite: <code>pnpm run dev</code></li>
                <li>Verifica en DevTools &gt; Network que las peticiones van a la URL correcta</li>
                <li>Refresca esta página después de que el backend esté corriendo</li>
              </ol>
            </div>
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
        ) : emptyDb ? (
          <div className="error-message empty-db-error">
            <p><strong>Base de datos vacía</strong></p>
            <p>{errorMessage}</p>
            <div className="error-instructions">
              <p><strong>Pasos para solucionar:</strong></p>
              <ol>
                <li>Arranca el backend si no está corriendo (ver instrucciones arriba)</li>
                <li>Ejecuta el pipeline de ingestión para poblar la base de datos:</li>
                <li className="code-block">python scripts/populate_database.py</li>
                <li>o</li>
                <li className="code-block">poetry run python -m app.scripts.populate_database</li>
                <li>Espera a que termine la ingestión de datos</li>
                <li>Verifica que los endpoints devuelven datos con:</li>
                <li className="code-block">python scripts/verify_endpoints.py</li>
                <li>Refresca esta página después de poblar los datos</li>
              </ol>
            </div>
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

