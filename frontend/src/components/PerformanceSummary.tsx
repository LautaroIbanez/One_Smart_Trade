import { usePerformanceSummary } from '../api/hooks'
import './PerformanceSummary.css'

function PerformanceSummary() {
  const { data, isLoading, error } = usePerformanceSummary()

  if (isLoading) {
    return (
      <div className="performance-summary" role="status" aria-live="polite">
        <h2>Resumen de Performance</h2>
        <div className="loading">Cargando métricas...</div>
      </div>
    )
  }

  if (error || !data || data.status !== 'success') {
    return null
  }

  const metrics = data.metrics || {}

  return (
    <div className="performance-summary">
      <h2>Resumen de Performance (Backtesting)</h2>
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
      {data.report_path && (
        <div className="report-link">
          <a href={data.report_path} target="_blank" rel="noreferrer">
            Ver reporte completo
          </a>
        </div>
      )}
    </div>
  )
}

export default PerformanceSummary

