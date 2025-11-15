import { useMemo, useState } from 'react'
import { format, parseISO } from 'date-fns'
import AuditTrailModal from './AuditTrailModal'
import './HistoryRow.css'

interface Recommendation {
  id?: number | string
  timestamp: string
  signal: string
  current_price?: number
  entry_price?: number
  exit_price?: number
  confidence?: number
  exit_reason?: string
  status?: string
  return_pct?: number
  pnl_pct?: number
  narrative?: string | string[]
  metrics?: {
    max_drawdown?: number
    duration_days?: number
    volatility?: number
    sharpe?: number
  }
  stop_loss_take_profit?: {
    stop_loss?: number
    take_profit?: number
  }
}

interface HistoryRowProps {
  recommendation: Recommendation
  isExpanded: boolean
  onExpand: () => void
}

function HistoryRow({ recommendation, isExpanded, onExpand }: HistoryRowProps) {
  const [showAuditTrail, setShowAuditTrail] = useState(false)
  const outcome = recommendation.exit_reason || recommendation.status || 'open'
  const returnPct = recommendation.return_pct || recommendation.pnl_pct || 0
  const confidence = recommendation.confidence || 0

  const outcomeClass = useMemo(() => {
    if (outcome.toLowerCase().includes('tp') || outcome.toLowerCase().includes('profit')) {
      return 'outcome-tp'
    }
    if (outcome.toLowerCase().includes('sl') || outcome.toLowerCase().includes('loss')) {
      return 'outcome-sl'
    }
    if (outcome.toLowerCase().includes('manual')) {
      return 'outcome-manual'
    }
    return 'outcome-open'
  }, [outcome])

  const returnClass = useMemo(() => {
    if (returnPct > 0) return 'return-positive'
    if (returnPct < 0) return 'return-negative'
    return 'return-neutral'
  }, [returnPct])

  return (
    <>
      <tr className={`history-row ${isExpanded ? 'expanded' : ''}`} onClick={onExpand}>
        <td>{format(parseISO(recommendation.timestamp), 'dd/MM/yyyy HH:mm')}</td>
        <td>
          <span className={`signal-badge signal-${recommendation.signal.toLowerCase()}`}>
            {recommendation.signal}
          </span>
        </td>
        <td>
          {recommendation.entry_price ? (
            <>
              <div>Entrada: ${recommendation.entry_price.toLocaleString()}</div>
              {recommendation.exit_price && (
                <div className="exit-price">Salida: ${recommendation.exit_price.toLocaleString()}</div>
              )}
            </>
          ) : (
            `$${recommendation.current_price?.toLocaleString() || 'N/A'}`
          )}
        </td>
        <td>
          <div className="confidence-bar">
            <div
              className="confidence-fill"
              style={{ width: `${confidence}%` }}
              role="progressbar"
              aria-valuenow={confidence}
              aria-valuemin={0}
              aria-valuemax={100}
            />
            <span className="confidence-text">{confidence.toFixed(1)}%</span>
          </div>
        </td>
        <td>
          <span className={`outcome-badge ${outcomeClass}`}>{outcome}</span>
        </td>
        <td className={returnClass}>
          {returnPct > 0 ? '+' : ''}
          {returnPct.toFixed(2)}%
        </td>
        <td>
          <button
            type="button"
            className={`expand-button ${isExpanded ? 'expanded' : ''}`}
            onClick={(e) => {
              e.stopPropagation()
              onExpand()
            }}
            aria-label={isExpanded ? 'Contraer detalles' : 'Expandir detalles'}
            aria-expanded={isExpanded}
          >
            {isExpanded ? '▼' : '▶'}
          </button>
        </td>
      </tr>
      {isExpanded && (
        <tr className="history-row-details">
          <td colSpan={7}>
            <div className="details-content">
              {recommendation.narrative && (
                <div className="details-section">
                  <h4>Narrativa</h4>
                  {Array.isArray(recommendation.narrative) ? (
                    <ul>
                      {recommendation.narrative.map((item, index) => (
                        <li key={index}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>{recommendation.narrative}</p>
                  )}
                </div>
              )}

              {recommendation.metrics && (
                <div className="details-section">
                  <h4>Métricas</h4>
                  <div className="metrics-grid">
                    {recommendation.metrics.max_drawdown !== undefined && (
                      <div className="metric-item">
                        <span className="metric-label">Max Drawdown:</span>
                        <span className="metric-value">{recommendation.metrics.max_drawdown.toFixed(2)}%</span>
                      </div>
                    )}
                    {recommendation.metrics.duration_days !== undefined && (
                      <div className="metric-item">
                        <span className="metric-label">Duración:</span>
                        <span className="metric-value">{recommendation.metrics.duration_days} días</span>
                      </div>
                    )}
                    {recommendation.metrics.volatility !== undefined && (
                      <div className="metric-item">
                        <span className="metric-label">Volatilidad:</span>
                        <span className="metric-value">{recommendation.metrics.volatility.toFixed(2)}%</span>
                      </div>
                    )}
                    {recommendation.metrics.sharpe !== undefined && (
                      <div className="metric-item">
                        <span className="metric-label">Sharpe Ratio:</span>
                        <span className="metric-value">{recommendation.metrics.sharpe.toFixed(2)}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {recommendation.stop_loss_take_profit && (
                <div className="details-section">
                  <h4>Niveles de Riesgo</h4>
                  <div className="levels-info">
                    {recommendation.stop_loss_take_profit.stop_loss && (
                      <div className="level-item">
                        <span className="level-label">Stop Loss:</span>
                        <span className="level-value stop-loss">
                          ${recommendation.stop_loss_take_profit.stop_loss.toLocaleString()}
                        </span>
                      </div>
                    )}
                    {recommendation.stop_loss_take_profit.take_profit && (
                      <div className="level-item">
                        <span className="level-label">Take Profit:</span>
                        <span className="level-value take-profit">
                          ${recommendation.stop_loss_take_profit.take_profit.toLocaleString()}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              <div className="details-section">
                <div className="details-section-header">
                  <h4>Información General</h4>
                  {recommendation.id && (
                    <button
                      type="button"
                      className="audit-trail-button"
                      onClick={() => setShowAuditTrail(true)}
                    >
                      🔍 Ver Rastro de Auditoría
                    </button>
                  )}
                </div>
                <div className="info-grid">
                  <div className="info-item">
                    <span className="info-label">Fecha:</span>
                    <span className="info-value">
                      {format(parseISO(recommendation.timestamp), 'PPpp')}
                    </span>
                  </div>
                  {recommendation.entry_price && (
                    <div className="info-item">
                      <span className="info-label">Precio de Entrada:</span>
                      <span className="info-value">${recommendation.entry_price.toLocaleString()}</span>
                    </div>
                  )}
                  {recommendation.exit_price && (
                    <div className="info-item">
                      <span className="info-label">Precio de Salida:</span>
                      <span className="info-value">${recommendation.exit_price.toLocaleString()}</span>
                    </div>
                  )}
                  <div className="info-item">
                    <span className="info-label">Retorno:</span>
                    <span className={`info-value ${returnClass}`}>
                      {returnPct > 0 ? '+' : ''}
                      {returnPct.toFixed(2)}%
                    </span>
                  </div>
                  <div className="info-item">
                    <span className="info-label">Confianza:</span>
                    <span className="info-value">{confidence.toFixed(1)}%</span>
                  </div>
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
      {recommendation.id && (
        <AuditTrailModal
          recommendationId={Number(recommendation.id)}
          isOpen={showAuditTrail}
          onClose={() => setShowAuditTrail(false)}
        />
      )}
    </>
  )
}

export default HistoryRow

