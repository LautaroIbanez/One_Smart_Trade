import { useMemo } from 'react'
import { usePerformanceSummary, isTimeoutError, getErrorMessage } from '../api/hooks'
import './PerformanceSummary.css'

function PerformanceSummary() {
  const { data, isLoading, error } = usePerformanceSummary()

  // Extract data from main payload or fallback_summary
  const effectiveData = useMemo(() => {
    if (!data) return null
    
    // If status is error but we have fallback_summary, use it
    if (data.status === 'error' && (data as any).fallback_summary) {
      const fallback = (data as any).fallback_summary
      return {
        ...data,
        metrics: data.metrics || fallback.metrics || {},
        period: data.period || fallback.period || null,
        report_path: data.report_path || fallback.report_path || null,
        _isDegraded: true,
        _degradedMessage: data.message || 'Datos en modo degradado',
      }
    }
    
    return data
  }, [data])

  const isDegraded = (effectiveData as any)?._isDegraded === true

  if (isLoading) {
    return (
      <div className="performance-summary" role="status" aria-live="polite">
        <h2>Resumen de Performance</h2>
        <div className="loading">Cargando métricas...</div>
      </div>
    )
  }

  if (error) {
    const isTimeout = isTimeoutError(error)
    const errorMessage = getErrorMessage(error)
    return (
      <div className="performance-summary error" role="alert" aria-live="assertive">
        <h2>Resumen de Performance</h2>
        <div className="error-message">
          {isTimeout ? (
            <div className="timeout-error">
              <p><strong>⏱️ Tiempo de espera excedido</strong></p>
              <p>El backend está ocupado procesando la solicitud. Por favor, intenta nuevamente en unos momentos.</p>
            </div>
          ) : (
            <div className="error-details">
              <p><strong>❌ Error al cargar métricas</strong></p>
              <p>{errorMessage}</p>
            </div>
          )}
        </div>
      </div>
    )
  }

  if (!effectiveData && !data) {
    return null
  }

  // Show component even in degraded mode if we have metrics
  const metrics = effectiveData?.metrics || {}
  const hasMetrics = Object.keys(metrics).length > 0

  if (!hasMetrics && !isDegraded) {
    return null
  }

  return (
    <div className="performance-summary">
      <h2>Resumen de Performance (Backtesting)</h2>
      {isDegraded && (
        <div className="degraded-mode-banner" role="status" aria-live="polite">
          <p>
            ⚠️ <strong>Modo degradado:</strong>{' '}
            {(effectiveData as any)?._degradedMessage || 'Mostrando métricas almacenadas.'}
          </p>
        </div>
      )}
      {hasMetrics ? (
        <>
          <div className="metrics-grid">
            <div className="metric-item">
              <span className="metric-label">CAGR</span>
              <span className="metric-value">{metrics.cagr?.toFixed(2)}%</span>
            </div>
            <div className="metric-item">
              <span className="metric-label">Sharpe</span>
              <span className="metric-value">{metrics.sharpe?.toFixed(2)}</span>
            </div>
            <div className="metric-item">
              <span className="metric-label">Max DD</span>
              <span className="metric-value">{metrics.max_drawdown?.toFixed(2)}%</span>
            </div>
            <div className="metric-item">
              <span className="metric-label">Win Rate</span>
              <span className="metric-value">{metrics.win_rate?.toFixed(1)}%</span>
            </div>
            <div className="metric-item">
              <span className="metric-label">Profit Factor</span>
              <span className="metric-value">{metrics.profit_factor?.toFixed(2)}</span>
            </div>
            <div className="metric-item">
              <span className="metric-label">Total Trades</span>
              <span className="metric-value">{metrics.total_trades || 0}</span>
            </div>
          </div>
          {effectiveData?.report_path ? (
            <div className="report-link">
              <a href={effectiveData.report_path} target="_blank" rel="noreferrer">
                Ver reporte completo
              </a>
            </div>
          ) : (
            <div className="no-metrics-placeholder">
              <p>⚠️ Métricas no disponibles en modo degradado</p>
              <p>Los datos frescos no están disponibles y no hay métricas almacenadas para mostrar.</p>
            </div>
          )}
        </>
      ) : (
        <div className="no-metrics-placeholder">
          <p>⚠️ Métricas no disponibles</p>
          <p>No se encontraron métricas para mostrar.</p>
        </div>
      )}
    </div>
  )
}

export default PerformanceSummary

