import { useState } from 'react'
import { useInvalidateAll, useTodayRecommendation, useGenerateRecommendation, isTimeoutError, isBackendDown, isEmptyDatabase, getErrorMessage } from '../api/hooks'
import RiskBadge from './RiskBadge'
import { ContextualArticles } from './ContextualArticle'
import './RecommendationCard.css'

const DEFAULT_USER_ID = '00000000-0000-0000-0000-000000000001'

function RecommendationCard() {
  const [isRetrying, setIsRetrying] = useState(false)
  const { data, isLoading, error, refetch, isRefetching } = useTodayRecommendation()
  const invalidateAll = useInvalidateAll()
  const generateRecommendation = useGenerateRecommendation()

  const handleRetry = async () => {
    setIsRetrying(true)
    try {
      // Invalidate all queries first to clear cache
      await invalidateAll()
      // Then refetch the current query
      await refetch()
    } catch (err) {
      console.error('Error retrying recommendation:', err)
    } finally {
      setIsRetrying(false)
    }
  }

  const handleGenerate = async () => {
    try {
      await generateRecommendation.mutateAsync()
      // After successful generation, refetch to get the new recommendation
      await invalidateAll()
      await refetch()
    } catch (err) {
      console.error('Error generating recommendation:', err)
      // Error is accessible via generateRecommendation.error and will be shown in UI
    }
  }

  const isGenerating = generateRecommendation.isPending
  const generationError = generateRecommendation.error as any

  if (isLoading || isRefetching || isRetrying || isGenerating) {
    return (
      <div className="recommendation-card loading" role="status" aria-live="polite">
        <div className="loading-spinner">
          {isGenerating ? 'Generando recomendación...' : isRetrying ? 'Reintentando...' : 'Cargando recomendación...'}
        </div>
      </div>
    )
  }

  if (error) {
    const isTimeout = isTimeoutError(error)
    const backendDown = isBackendDown(error)
    const emptyDb = isEmptyDatabase(error)
    const errorMessage = getErrorMessage(error)
    
    return (
      <div className="recommendation-card error" role="alert" aria-live="assertive">
        {isTimeout ? (
          <>
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
          </>
        ) : backendDown ? (
          <>
            <p><strong>🔴 Backend no disponible</strong></p>
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
                <li>Si el backend está en otro host/puerto, configura <code>VITE_API_BASE_URL</code> en <code>frontend/.env</code>:</li>
                <li className="code-block">VITE_API_BASE_URL=http://127.0.0.1:8000</li>
                <li className="code-block"># O para backend remoto: VITE_API_BASE_URL=https://api.example.com</li>
                <li>Después de cambiar <code>.env</code>, reinicia Vite: <code>pnpm run dev</code></li>
                <li>Verifica en DevTools &gt; Network que las peticiones van a la URL correcta</li>
                <li>Refresca esta página después de que el backend esté corriendo</li>
              </ol>
            </div>
          </>
        ) : emptyDb ? (
          <>
            <p><strong>📭 Base de datos vacía</strong></p>
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
          </>
        ) : (
          <>
            <p><strong>❌ Error al cargar recomendación</strong></p>
            <p>{errorMessage}</p>
          </>
        )}
        <button 
          onClick={handleRetry} 
          type="button" 
          aria-label="Reintentar carga"
          disabled={isRetrying}
        >
          {isRetrying ? 'Reintentando...' : 'Reintentar'}
        </button>
      </div>
    )
  }

  // Handle null/undefined data with safe defaults
  if (!data) {
    return (
      <div className="recommendation-card no-data-state">
        <div className="no-data-header">
          <h2>📊 Sin Recomendación Disponible</h2>
        </div>
        <div className="no-data-content">
          <p className="no-data-message">
            No se pudo cargar la recomendación. El backend puede estar procesando datos o en modo degradado.
          </p>
          <div className="no-data-actions" style={{ display: 'flex', gap: '1rem', justifyContent: 'center', marginTop: '1rem' }}>
            <button 
              onClick={handleRetry} 
              type="button" 
              aria-label="Reintentar carga"
              disabled={isRetrying}
              className="guardrail-retry-button"
            >
              {isRetrying ? 'Reintentando...' : '🔄 Reintentar'}
            </button>
            <button 
              onClick={handleGenerate} 
              type="button" 
              aria-label="Generar recomendación"
              disabled={isGenerating || isRetrying}
              className="guardrail-retry-button"
              style={{ 
                backgroundColor: isGenerating ? '#9ca3af' : '#10b981',
              }}
            >
              {isGenerating ? '⏳ Generando...' : '✨ Generar Recomendación'}
            </button>
          </div>
        </div>
      </div>
    )
  }
  
  // Check if this is a dev fallback/degraded recommendation
  const isDevFallback = (data as any)?.dev_fallback === true || (data as any)?.risk_metrics?.dev_fallback === true
  const isDegradedMode = (data as any)?.degraded_mode === true || (data as any)?.risk_metrics?.degraded_mode === true

  // Type guard: Check if this is a fallback response (no_data) without required fields
  const isFallbackResponse = (data: any): boolean => {
    return data?.status === 'no_data' || 
           !data?.signal || 
           typeof data?.current_price !== 'number' || 
           !data?.entry_range || 
           !data?.stop_loss_take_profit
  }

  // Handle no_data status early - before accessing fields that don't exist in fallback response
  if (data.status === 'no_data' || isFallbackResponse(data)) {
    return (
      <div className="recommendation-card no-data-state">
        <div className="no-data-header">
          <h2>📊 Sin Recomendación Disponible</h2>
        </div>
        <div className="no-data-content">
          <p className="no-data-message">
            {data.reason || 'Aún no se ha generado una recomendación para hoy.'}
          </p>
          {data.data_recency && (
            <div className="no-data-details">
              {data.data_recency.status === 'missing' ? (
                <p className="no-data-hint">
                  No hay recomendaciones generadas aún. Las recomendaciones se generan automáticamente todos los días a las 12:00 UTC.
                </p>
              ) : data.data_recency.status === 'stale' && data.data_recency.days_since_release !== undefined ? (
                <p className="no-data-hint">
                  La última recomendación disponible es de hace {data.data_recency.days_since_release} día(s).
                  {data.latest_available_date && (
                    <> Última disponible: {new Date(data.latest_available_date).toLocaleDateString('es-ES')}</>
                  )}
                </p>
              ) : null}
            </div>
          )}
          {data.allow_replay_hint && (
            <p className="no-data-replay-hint">
              💡 <em>Nota: Puedes generar una recomendación on-demand usando el botón de abajo (modo desarrollo/paper trading).</em>
            </p>
          )}
          <div className="no-data-actions" style={{ display: 'flex', gap: '1rem', justifyContent: 'center', marginTop: '1rem' }}>
            <button 
              onClick={handleGenerate} 
              type="button" 
              aria-label="Generar recomendación"
              disabled={isGenerating || isRetrying}
              className="guardrail-retry-button"
              style={{ 
                backgroundColor: isGenerating ? '#9ca3af' : '#10b981',
              }}
            >
              {isGenerating ? '⏳ Generando...' : '✨ Generar Recomendación'}
            </button>
            <button 
              onClick={handleRetry} 
              type="button" 
              aria-label="Reintentar carga"
              disabled={isRetrying || isGenerating}
              className="guardrail-retry-button"
            >
              {isRetrying ? 'Reintentando...' : '🔄 Reintentar'}
            </button>
          </div>
          {generationError && (
            <div className="no-data-error" style={{ marginTop: '1rem', padding: '0.75rem', backgroundColor: 'rgba(239, 68, 68, 0.1)', borderRadius: '0.5rem', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
              <p style={{ margin: 0, color: '#ef4444', fontSize: '0.875rem', fontWeight: 600 }}>
                ❌ Error al generar recomendación
              </p>
              <p style={{ margin: '0.5rem 0 0 0', color: '#fca5a5', fontSize: '0.875rem' }}>
                {generationError?.response?.data?.detail?.message || 
                 generationError?.response?.data?.detail?.reason || 
                 (generationError?.response?.data?.detail && typeof generationError.response.data.detail === 'string' ? generationError.response.data.detail : null) ||
                 (generationError instanceof Error ? generationError.message : 'Error desconocido al generar la recomendación')}
              </p>
              {generationError?.response?.data?.detail?.status === 'manual_replay_disabled' && (
                <div style={{ margin: '0.5rem 0 0 0', padding: '0.5rem', backgroundColor: 'rgba(251, 191, 36, 0.1)', borderRadius: '0.25rem', border: '1px solid rgba(251, 191, 36, 0.3)' }}>
                  <p style={{ margin: 0, color: '#f59e0b', fontSize: '0.75rem', fontStyle: 'italic' }}>
                    ⚠️ El modo replay manual no está habilitado en el backend. Para habilitarlo, configura <code>ALLOW_MANUAL_REPLAY=True</code> en las variables de entorno del backend.
                  </p>
                </div>
              )}
              {generationError?.response?.data?.detail?.status === 'insufficient_history' && (
                <p style={{ margin: '0.5rem 0 0 0', color: '#fca5a5', fontSize: '0.75rem', fontStyle: 'italic' }}>
                  En modo desarrollo, asegúrate de que AUTO_SHUTDOWN_ALLOW_MISSING_DATA_IN_DEV esté habilitado para permitir generación sin historial.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    )
  }

  const formatTimeRemaining = (seconds: number) => {
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const secs = seconds % 60
    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs}s`
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`
    } else {
      return `${secs}s`
    }
  }

  // Handle cooldown status
  if (data.status === 'cooldown') {
    return (
      <>
        <div className="recommendation-card cooldown-blocked">
          <div className="cooldown-blocked-header">
            <h2>⏸️ Período de Enfriamiento Activo</h2>
          </div>
          <div className="cooldown-blocked-content">
            <p className="cooldown-message">{data.reason || "Operaciones bloqueadas temporalmente"}</p>
            {data.cooldown_remaining_seconds && (
              <p className="cooldown-time">
                Tiempo restante: <strong>{formatTimeRemaining(data.cooldown_remaining_seconds)}</strong>
              </p>
            )}
            {data.cooldown_until && (
              <p className="cooldown-until">
                Las operaciones estarán disponibles nuevamente el: {new Date(data.cooldown_until).toLocaleString('es-ES')}
              </p>
            )}
            <p className="cooldown-explanation">
              Durante este período, se bloquea la generación de nuevas señales para evitar decisiones emocionales tras rachas adversas o sobreoperación.
            </p>
          </div>
        </div>
        {data.contextual_articles && data.contextual_articles.length > 0 && (
          <ContextualArticles articles={data.contextual_articles} userId={DEFAULT_USER_ID} />
        )}
      </>
    )
  }

  // Handle shutdown status
  if (data.status === 'shutdown') {
    return (
      <div className="recommendation-card shutdown-blocked">
        <div className="shutdown-blocked-header">
          <h2>🛑 Sistema en Pausa</h2>
        </div>
        <div className="shutdown-blocked-content">
          <p className="shutdown-message">{data.reason || "Operaciones suspendidas"}</p>
          <p className="shutdown-explanation">
            El sistema ha detectado condiciones que requieren una revisión manual antes de continuar operando.
          </p>
        </div>
      </div>
    )
  }

  // Handle data_stale status - This is a valid guardrail state, not an error
  if (data.status === 'data_stale') {
    return (
      <div className="recommendation-card guardrail-blocked">
        <div className="guardrail-blocked-header">
          <h2>⏰ Datos Desactualizados (Guardrail Activo)</h2>
        </div>
        <div className="guardrail-blocked-content">
          <p className="guardrail-message">{data.reason || "Los datos de mercado están desactualizados"}</p>
          <p className="guardrail-explanation">
            {data.interval && data.latest_timestamp && data.threshold_minutes ? (
              <>
                El intervalo <strong>{data.interval}</strong> tiene datos más antiguos que el umbral permitido ({data.threshold_minutes} minutos).
                <br />
                Última actualización: {new Date(data.latest_timestamp).toLocaleString('es-ES')}
              </>
            ) : (
              "Los datos de mercado necesitan ser actualizados antes de generar una recomendación."
            )}
          </p>
          <div className="guardrail-instructions">
            <p><strong>Pasos para solucionar:</strong></p>
            <ol>
              <li>Verifica que la última ingesta completó sin errores</li>
              <li>Si hay data_stale, reejecuta el pipeline para refrescar los datos:</li>
              <li className="code-block">python scripts/populate_database.py</li>
              <li>o verifica manualmente con:</li>
              <li className="code-block">curl http://localhost:8000/api/v1/recommendation/today</li>
              <li>Espera a que termine el backfill (puede tardar varios minutos)</li>
              <li>Refresca esta página después de que los datos estén actualizados</li>
            </ol>
            <p className="guardrail-note">
              💡 <strong>Nota:</strong> Este es un guardrail válido del sistema. La señal no se genera cuando los datos no están frescos para proteger la calidad de las recomendaciones.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
            <button 
              onClick={handleRetry} 
              type="button" 
              aria-label="Reintentar después del backfill"
              disabled={isRetrying}
              className="guardrail-retry-button"
            >
              {isRetrying ? 'Reintentando...' : '🔄 Reintentar'}
            </button>
            <button 
              onClick={handleGenerate} 
              type="button" 
              aria-label="Forzar generación (puede ignorar guardrails)"
              disabled={isGenerating}
              className="guardrail-retry-button"
              style={{ backgroundColor: '#10b981' }}
            >
              {isGenerating ? 'Generando...' : '✨ Forzar Generación'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Handle data_gaps status - This is a valid guardrail state, not an error
  if (data.status === 'data_gaps') {
    return (
      <div className="recommendation-card guardrail-blocked">
        <div className="guardrail-blocked-header">
          <h2>📊 Faltan Datos (Gaps Detectados - Guardrail Activo)</h2>
        </div>
        <div className="guardrail-blocked-content">
          <p className="guardrail-message">{data.reason || "Se detectaron gaps en los datos de mercado"}</p>
          <p className="guardrail-explanation">
            {data.interval && data.gaps ? (
              <>
                El intervalo <strong>{data.interval}</strong> tiene {data.gaps.length} gap(s) que exceden la tolerancia permitida ({data.tolerance_candles} velas).
                <br />
                Se requiere ejecutar la ingesta de datos para llenar los gaps antes de generar una recomendación.
              </>
            ) : (
              "Faltan velas en los datos de mercado. Ejecuta la ingesta de datos para completar la información necesaria."
            )}
          </p>
          <div className="guardrail-instructions">
            <p><strong>Pasos para solucionar:</strong></p>
            <ol>
              <li>Verifica que la última ingesta completó sin errores</li>
              <li>Si hay data_gaps, reejecuta el pipeline para parchear los huecos:</li>
              <li className="code-block">python scripts/populate_database.py</li>
              <li>Espera a que termine la ingestión de datos</li>
              <li>Verifica que los endpoints devuelven datos con:</li>
              <li className="code-block">python scripts/verify_endpoints.py</li>
              <li>Refresca esta página después de que los gaps estén resueltos</li>
            </ol>
            <p className="guardrail-note">
              💡 <strong>Nota:</strong> Este es un guardrail válido del sistema. Los gaps en los datos pueden afectar la calidad de las señales, por lo que se bloquea la generación hasta resolverlos.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
            <button 
              onClick={handleRetry} 
              type="button" 
              aria-label="Reintentar después de la ingesta"
              disabled={isRetrying}
              className="guardrail-retry-button"
            >
              {isRetrying ? 'Reintentando...' : '🔄 Reintentar'}
            </button>
            <button 
              onClick={handleGenerate} 
              type="button" 
              aria-label="Forzar generación"
              disabled={isGenerating}
              className="guardrail-retry-button"
              style={{ backgroundColor: '#10b981' }}
            >
              {isGenerating ? 'Generando...' : '✨ Forzar Generación'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Handle insufficient history guardrail - This is a valid guardrail state, not an error
  if (data.status === 'insufficient_history') {
    return (
      <div className="recommendation-card guardrail-blocked">
        <div className="guardrail-blocked-header">
          <h2>📉 Historial Insuficiente (Guardrail Activo)</h2>
        </div>
        <div className="guardrail-blocked-content">
          <p className="guardrail-message">{data.reason || data.message || 'No hay trades suficientes para calcular riesgo y rendimiento.'}</p>
          <p className="guardrail-explanation">
            El sistema necesita historial de trades suficiente para calcular métricas de riesgo (Sharpe, hit rate) antes de generar señales accionables.
          </p>
          <ul className="guardrail-details">
            {data.required_trades && (
              <li>
                Trades requeridos: <strong>{data.required_trades}</strong>
              </li>
            )}
            {data.lookback_trades && (
              <li>
                Ventana considerada: <strong>{data.lookback_trades}</strong> trades recientes
              </li>
            )}
          </ul>
          <div className="guardrail-instructions">
            <p><strong>Pasos para solucionar:</strong></p>
            <ol>
              <li>En las primeras ejecuciones, el sistema no tendrá histórico suficiente</li>
              <li>Ejecuta el pipeline para generar recomendaciones y acumular historial:</li>
              <li className="code-block">python scripts/populate_database.py</li>
              <li>Espera a que termine (puede tardar varios minutos en primeras ejecuciones)</li>
              <li>El sistema devolverá HOLD/503 hasta acumular suficientes datos</li>
              <li>Verifica el estado con:</li>
              <li className="code-block">curl http://localhost:8000/api/v1/recommendation/today</li>
              <li>Revisa el JSON de <code>status/reason</code> para confirmar el progreso</li>
              <li>Una vez haya historial suficiente, las señales BUY/SELL comenzarán a generarse</li>
            </ol>
            <p className="guardrail-note">
              💡 <strong>Nota:</strong> Este es un guardrail válido del sistema. En modo desarrollo/paper trading, puedes habilitar <code>HOLD_FALLBACK_TO_LAST_SIGNAL</code> para mostrar la última señal válida mientras se acumula historial.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '1rem', marginTop: '1rem' }}>
            <button
              onClick={handleRetry}
              type="button"
              aria-label="Reintentar después de cargar historial"
              disabled={isRetrying}
              className="guardrail-retry-button"
            >
              {isRetrying ? 'Reintentando...' : '🔄 Reintentar'}
            </button>
            <button
              onClick={handleGenerate}
              type="button"
              aria-label="Forzar generación (puede usar fallback si está habilitado)"
              disabled={isGenerating}
              className="guardrail-retry-button"
              style={{ backgroundColor: '#10b981' }}
            >
              {isGenerating ? 'Generando...' : '✨ Forzar Generación'}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // Handle leverage hard stop status
  if (data.status === 'leverage_hard_stop') {
    return (
      <>
        <div className="recommendation-card leverage-blocked">
          <div className="leverage-blocked-header">
            <h2>🛑 Hard Stop: Apalancamiento Excesivo</h2>
          </div>
          <div className="leverage-blocked-content">
            <p className="leverage-message">{data.reason || "Operaciones bloqueadas por apalancamiento excesivo"}</p>
            {data.effective_leverage !== undefined && (
              <div className="leverage-details">
                <p className="leverage-value">
                  Apalancamiento actual: <strong>{data.effective_leverage.toFixed(2)}×</strong>
                </p>
                {data.current_equity !== undefined && (
                  <p className="leverage-equity">
                    Equity disponible: ${data.current_equity.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </p>
                )}
                {data.total_notional !== undefined && (
                  <p className="leverage-notional">
                    Valor nominal total: ${data.total_notional.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </p>
                )}
              </div>
            )}
            {data.hard_stop_since && (
              <p className="leverage-since">
                Bloqueo activo desde: {new Date(data.hard_stop_since).toLocaleString('es-ES')}
              </p>
            )}
            <p className="leverage-explanation">
              Reduzca sus posiciones abiertas para disminuir el apalancamiento efectivo por debajo de 3× antes de continuar operando.
            </p>
          </div>
        </div>
        {data.contextual_articles && data.contextual_articles.length > 0 && (
          <ContextualArticles articles={data.contextual_articles} userId={DEFAULT_USER_ID} />
        )}
      </>
    )
  }

  // Handle capital missing status
  if (data.status === 'capital_missing') {
    return (
      <div className="recommendation-card capital-missing-blocked">
        <div className="capital-missing-blocked-header">
          <h2>⚠️ Señal Bloqueada por Seguridad: Capital No Validado</h2>
        </div>
        <div className="capital-missing-blocked-content">
          <p className="capital-missing-message">{data.reason || "Debes conectar tu cuenta o ingresar capital para recibir señales"}</p>
          <p className="capital-missing-explanation">
            Para proteger tu capital y recibir recomendaciones personalizadas, necesitamos validar tu capital disponible. 
            Esto nos permite calcular el tamaño de posición adecuado según tu perfil de riesgo.
          </p>
          <div className="capital-missing-actions">
            <p className="capital-missing-instructions">
              <strong>Opciones:</strong>
            </p>
            <ul className="capital-missing-list">
              <li>Conecta tu cuenta de trading para sincronizar tu capital automáticamente</li>
              <li>O ingresa tu capital manualmente usando el endpoint <code>/api/v1/risk/sizing</code></li>
            </ul>
          </div>
          {data.requires_capital_input && (
            <p className="capital-missing-note">
              <em>Una vez que valides tu capital, podrás recibir señales de trading personalizadas.</em>
            </p>
          )}
          <button 
            onClick={handleRetry} 
            type="button" 
            aria-label="Reintentar después de validar capital"
            disabled={isRetrying}
            className="guardrail-retry-button"
          >
            {isRetrying ? 'Reintentando...' : '🔄 Reintentar'}
          </button>
        </div>
      </div>
    )
  }

  // Handle daily risk limit exceeded
  if (data.status === 'daily_risk_limit_exceeded') {
    return (
      <div className="recommendation-card risk-limit-blocked">
        <div className="risk-limit-blocked-header">
          <h2>🚫 Riesgo Diario Excedido</h2>
        </div>
        <div className="risk-limit-blocked-content">
          <p className="risk-limit-message">{data.message || data.reason || "Has alcanzado el límite diario de riesgo"}</p>
          {data.daily_limit_pct !== undefined && (
            <div className="risk-limit-details">
              <p className="risk-limit-value">
                Límite diario: <strong>{data.daily_limit_pct}%</strong> del equity
              </p>
              {data.daily_risk_pct !== undefined && (
                <p className="risk-limit-current">
                  Riesgo acumulado hoy: <strong>{data.daily_risk_pct.toFixed(2)}%</strong>
                </p>
              )}
            </div>
          )}
          <p className="risk-limit-explanation">
            Has alcanzado el límite diario de riesgo (3% del equity). No se pueden generar nuevas señales hasta el siguiente día.
            Este límite está diseñado para proteger tu capital y prevenir sobreoperación.
          </p>
          <p className="risk-limit-note">
            <em>El límite se reinicia cada 24 horas. Revisa tus posiciones abiertas y considera cerrar algunas antes de mañana.</em>
          </p>
          <button 
            onClick={handleRetry} 
            type="button" 
            aria-label="Reintentar carga"
            disabled={isRetrying}
            className="guardrail-retry-button"
          >
            {isRetrying ? 'Reintentando...' : '🔄 Reintentar'}
          </button>
        </div>
      </div>
    )
  }

  // Handle trade limit preventive
  if (data.status === 'trade_limit_preventive') {
    return (
      <>
        <div className="recommendation-card trade-limit-blocked">
          <div className="trade-limit-blocked-header">
            <h2>⏸️ Límite Preventivo Alcanzado</h2>
          </div>
          <div className="trade-limit-blocked-content">
            <p className="trade-limit-message">{data.reason || "Has alcanzado el límite preventivo de trades"}</p>
            {data.trades_count !== undefined && (
              <div className="trade-limit-details">
                <p className="trade-limit-value">
                  Trades realizados en 24h: <strong>{data.trades_count}</strong>
                </p>
                {data.max_trades_24h !== undefined && (
                  <p className="trade-limit-max">
                    Límite máximo: <strong>{data.max_trades_24h}</strong> trades
                  </p>
                )}
                {data.trades_remaining !== undefined && (
                  <p className="trade-limit-remaining">
                    Trades restantes: <strong>{data.trades_remaining}</strong>
                  </p>
                )}
              </div>
            )}
            <p className="trade-limit-explanation">
              Has realizado 7 trades en las últimas 24 horas. Para proteger tu capital y prevenir sobreoperación,
              debes esperar 12 horas antes de continuar. El límite preventivo está diseñado para evitar fatiga de decisión
              y decisiones emocionales.
            </p>
            <p className="trade-limit-note">
              <em>Usa este tiempo para revisar tus trades, leer material educativo y descansar.</em>
            </p>
          </div>
        </div>
        {data.contextual_articles && data.contextual_articles.length > 0 && (
          <ContextualArticles articles={data.contextual_articles} userId={DEFAULT_USER_ID} />
        )}
      </>
    )
  }

  // Display trades remaining indicator if available
  const tradeActivity = data.trade_activity
  const tradesRemaining = tradeActivity?.trades_remaining
  const tradesCount = tradeActivity?.trades_count
  const maxTrades24h = tradeActivity?.max_trades_24h
  const committedRiskPct = tradeActivity?.committed_risk_pct
  const dailyRiskLimitPct = tradeActivity?.daily_risk_limit_pct
  const dailyRiskWarningPct = tradeActivity?.daily_risk_warning_pct

  // Validate required fields exist before using them (type guard already ensures this, but extra safety)
  const signal = data.signal ?? 'HOLD'
  const isManualGeneration = data.risk_metrics?.manual_generation === true
  const signalClass = signal ? `signal-${signal.toLowerCase()}` : 'signal-hold'
  const currentPrice = data.current_price ?? 0
  const entryRange = data.entry_range ?? { min: 0, max: 0 }
  const stopLossTakeProfit = data.stop_loss_take_profit ?? { stop_loss: 0, take_profit: 0 }

  // If we somehow still don't have the minimum required data, show fallback
  if (!signal || !data.current_price || !data.entry_range || !data.stop_loss_take_profit) {
    return (
      <div className="recommendation-card no-data-state">
        <div className="no-data-header">
          <h2>⚠️ Datos Incompletos</h2>
        </div>
        <div className="no-data-content">
          <p className="no-data-message">
            La recomendación no incluye todos los datos necesarios para mostrarse.
          </p>
          <button 
            onClick={handleRetry} 
            type="button" 
            aria-label="Reintentar carga"
            disabled={isRetrying}
            className="guardrail-retry-button"
          >
            {isRetrying ? 'Reintentando...' : '🔄 Reintentar'}
          </button>
        </div>
      </div>
    )
  }

  // Check if this is a stale/fallback signal
  const isStale = data.is_stale === true
  const fallbackCause = data.fallback_cause
  const originalSignalDate = data.original_signal_date

  // Map fallback cause to user-friendly message
  const getFallbackCauseMessage = (cause: string | null | undefined): string => {
    if (!cause) return 'razón desconocida'
    const causeMap: Record<string, string> = {
      'insufficient_history': 'historial insuficiente',
      'guardrail_blocked': 'guardrails activados',
      'data_stale': 'datos desactualizados',
      'data_gaps': 'gaps en los datos',
    }
    return causeMap[cause] || cause
  }

  return (
    <div className="recommendation-card">
      <div className="recommendation-header" aria-label="Señal actual">
        <h2>Recomendación de Hoy</h2>
        <span className={`signal-badge ${signalClass}`}>{signal}</span>
      </div>
      
      {/* Dev fallback / Degraded mode banner */}
      {(isDevFallback || isDegradedMode || isManualGeneration) && (
        <div className="manual-generation-banner" role="alert" aria-live="polite" style={{ 
          margin: '1rem 0', 
          padding: '0.75rem', 
          backgroundColor: isDevFallback ? 'rgba(147, 51, 234, 0.1)' : 'rgba(251, 191, 36, 0.1)', 
          borderRadius: '0.5rem', 
          border: `1px solid ${isDevFallback ? 'rgba(147, 51, 234, 0.3)' : 'rgba(251, 191, 36, 0.3)'}` 
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '1.25rem' }}>{isDevFallback ? '🔧' : '🔧'}</span>
            <div>
              <p style={{ margin: 0, color: isDevFallback ? '#9333ea' : '#f59e0b', fontSize: '0.875rem', fontWeight: 600 }}>
                {isDevFallback ? '⚠️ Modo Desarrollo (Datos Fallback)' : 'Modo Manual / Degradado'}
              </p>
              <p style={{ margin: '0.25rem 0 0 0', color: isDevFallback ? '#a855f7' : '#d97706', fontSize: '0.75rem' }}>
                {isDevFallback 
                  ? 'Esta recomendación usa datos de respaldo generados en modo desarrollo. Los valores pueden no reflejar condiciones reales del mercado.'
                  : 'Esta recomendación fue generada manualmente (replay mode) para pruebas o paper trading. No es parte del pipeline automático diario.'}
              </p>
            </div>
          </div>
        </div>
      )}
      
      {/* Stale signal banner */}
      {isStale && (
        <div className="stale-signal-banner" role="alert" aria-live="polite">
          <div className="stale-signal-header">
            <span className="stale-signal-icon">⏰</span>
            <h3 className="stale-signal-title">Señal Histórica (Fallback)</h3>
          </div>
          <div className="stale-signal-content">
            <p className="stale-signal-message">
              Esta es una señal histórica que se está mostrando porque la señal del día es <strong>HOLD</strong> debido a{' '}
              <strong>{getFallbackCauseMessage(fallbackCause)}</strong>.
            </p>
            {originalSignalDate && (
              <p className="stale-signal-date">
                <strong>Fecha original de la señal:</strong> {new Date(originalSignalDate).toLocaleDateString('es-ES', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric'
                })}
              </p>
            )}
            <p className="stale-signal-warning">
              ⚠️ <strong>Advertencia:</strong> Los niveles de entrada, Stop Loss y Take Profit pueden estar desactualizados y no reflejar las condiciones actuales del mercado. Úsalos con precaución.
            </p>
          </div>
        </div>
      )}
      
      {/* Trades remaining and daily risk indicators */}
      {(tradesRemaining !== undefined || committedRiskPct !== undefined) && (
        <div className="trade-activity-indicators">
          {tradesRemaining !== undefined && maxTrades24h !== undefined && (
            <div className="trades-remaining-indicator" title={`Trades realizados en las últimas 24h: ${tradesCount || 0} de ${maxTrades24h}`}>
              <span className="indicator-label">Trades restantes:</span>
              <span className={`indicator-value ${tradesRemaining <= 1 ? 'warning' : ''}`}>
                {tradesRemaining} / {maxTrades24h}
              </span>
            </div>
          )}
          {committedRiskPct !== undefined && dailyRiskLimitPct !== undefined && (
            <div className="daily-risk-indicator" title={`Riesgo diario comprometido: ${committedRiskPct.toFixed(2)}% del equity`}>
              <span className="indicator-label">Riesgo diario:</span>
              <span className={`indicator-value ${committedRiskPct > (dailyRiskWarningPct || 2.0) ? 'warning' : ''} ${committedRiskPct > dailyRiskLimitPct ? 'danger' : ''}`}>
                {committedRiskPct.toFixed(2)}% / {dailyRiskLimitPct}%
              </span>
            </div>
          )}
        </div>
      )}
      <div className="recommendation-content">
        <div className="price-info">
          <span className="label">Precio Actual:</span>
          <span className="value">${currentPrice.toLocaleString()}</span>
        </div>
        <div className="entry-range">
          <span className="label">Rango de Entrada:</span>
          <span className="value">
            ${entryRange.min.toLocaleString()} - ${entryRange.max.toLocaleString()}
          </span>
        </div>
        <div className="sl-tp">
          <div className="sl-tp-item">
            <span className="label">Stop Loss:</span>
            <span className="value danger">${stopLossTakeProfit.stop_loss.toLocaleString()}</span>
          </div>
          <div className="sl-tp-item">
            <span className="label">Take Profit:</span>
            <span className="value success">${stopLossTakeProfit.take_profit.toLocaleString()}</span>
          </div>
        </div>
        <div className="confidence-group">
          <div className="confidence raw">
            <span className="label">Confianza Heurística:</span>
            <span className="value">{(data.confidence_raw ?? data.confidence).toFixed(1)}%</span>
            <small className="hint">Basada en la votación del ensemble antes de calibrar.</small>
          </div>
          <div
            className="confidence calibrated"
            title={
              data.confidence_band
                ? `Históricamente, señales similares acertaron entre ${data.confidence_band.lower.toFixed(
                    1,
                  )}% y ${data.confidence_band.upper.toFixed(1)}%.`
                : 'Calibración estadística basada en resultados históricos.'
            }
          >
            <span className="label">Confianza Calibrada:</span>
            <span className="value">
              {(data.confidence_calibrated ?? data.confidence_raw ?? data.confidence).toFixed(1)}%
            </span>
            {data.confidence_band && (
              <small className="hint">
                Históricamente: {data.confidence_band.lower.toFixed(1)}%–
                {data.confidence_band.upper.toFixed(1)}%
              </small>
            )}
          </div>
        </div>
        {data.recommended_risk_fraction !== undefined && (
          <RiskBadge riskFraction={data.recommended_risk_fraction} />
        )}
        <section aria-labelledby="analysis-heading" className="analysis">
          <h3 id="analysis-heading">Análisis profesional</h3>
          <p className="analysis-text">{data.analysis}</p>
        </section>
        {Array.isArray(data.signal_breakdown?.narrative) && data.signal_breakdown?.narrative.length > 0 && (
          <section aria-labelledby="drivers-heading" className="drivers">
            <h3 id="drivers-heading">Drivers de la señal</h3>
            <ul>
              {data.signal_breakdown.narrative.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        )}
        {data.disclaimer && (
          <div className="recommendation-disclaimer" role="note" aria-label="Disclaimer legal">
            <strong>⚠️ Aviso Legal:</strong> {data.disclaimer}
          </div>
        )}
      </div>
    </div>
  )
}

export default RecommendationCard

