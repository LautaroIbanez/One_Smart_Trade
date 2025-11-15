import { useState } from 'react'
import { useInvalidateAll, useTodayRecommendation } from '../api/hooks'
import RiskBadge from './RiskBadge'
import { ContextualArticles } from './ContextualArticle'
import './RecommendationCard.css'

const DEFAULT_USER_ID = '00000000-0000-0000-0000-000000000001'

function RecommendationCard() {
  const [isRetrying, setIsRetrying] = useState(false)
  const { data, isLoading, error, refetch, isRefetching } = useTodayRecommendation()
  const invalidateAll = useInvalidateAll()

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

  if (isLoading || isRefetching || isRetrying) {
    return (
      <div className="recommendation-card loading" role="status" aria-live="polite">
        <div className="loading-spinner">
          {isRetrying ? 'Reintentando...' : 'Cargando recomendación...'}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="recommendation-card error" role="alert" aria-live="assertive">
        <p>Error al cargar recomendación</p>
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

  if (!data) {
    return (
      <div className="recommendation-card">
        <p>No hay recomendación disponible</p>
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

  const signalClass = `signal-${data.signal.toLowerCase()}`

  return (
    <div className="recommendation-card">
      <div className="recommendation-header" aria-label="Señal actual">
        <h2>Recomendación de Hoy</h2>
        <span className={`signal-badge ${signalClass}`}>{data.signal}</span>
      </div>
      <div className="recommendation-content">
        <div className="price-info">
          <span className="label">Precio Actual:</span>
          <span className="value">${data.current_price.toLocaleString()}</span>
        </div>
        <div className="entry-range">
          <span className="label">Rango de Entrada:</span>
          <span className="value">
            ${data.entry_range.min.toLocaleString()} - ${data.entry_range.max.toLocaleString()}
          </span>
        </div>
        <div className="sl-tp">
          <div className="sl-tp-item">
            <span className="label">Stop Loss:</span>
            <span className="value danger">${data.stop_loss_take_profit.stop_loss.toLocaleString()}</span>
          </div>
          <div className="sl-tp-item">
            <span className="label">Take Profit:</span>
            <span className="value success">${data.stop_loss_take_profit.take_profit.toLocaleString()}</span>
          </div>
        </div>
        <div className="confidence">
          <span className="label">Confianza:</span>
          <span className="value">{data.confidence.toFixed(1)}%</span>
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

