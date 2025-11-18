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

  const signalClass = `signal-${data.signal.toLowerCase()}`

  return (
    <div className="recommendation-card">
      <div className="recommendation-header" aria-label="Señal actual">
        <h2>Recomendación de Hoy</h2>
        <span className={`signal-badge ${signalClass}`}>{data.signal}</span>
      </div>
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

