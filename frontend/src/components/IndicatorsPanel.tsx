import { useTodayRecommendation } from '../api/hooks'
import './IndicatorsPanel.css'

function IndicatorsPanel() {
  const { data, isLoading, error } = useTodayRecommendation()

  if (isLoading) {
    return (
      <div className="indicators-panel" role="status" aria-live="polite">
        <h2>Indicadores Clave</h2>
        <div className="loading">Cargando indicadores...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="indicators-panel" role="alert">
        <h2>Indicadores Clave</h2>
        <div className="error">Error al cargar indicadores</div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="indicators-panel">
        <h2>Indicadores Clave</h2>
        <div className="empty">No hay datos disponibles</div>
      </div>
    )
  }

  const indicators = data.indicators || {}
  const riskMetrics = data.risk_metrics || {}

  // Format indicator values for display
  const formatValue = (key: string, value: any): string => {
    if (typeof value === 'number') {
      // Format percentages for RSI, confidence-like values
      if (key.toLowerCase().includes('rsi') || key.toLowerCase().includes('stoch')) {
        return value.toFixed(2)
      }
      // Format large numbers with commas
      if (Math.abs(value) >= 1000) {
        return value.toLocaleString('en-US', { maximumFractionDigits: 2 })
      }
      // Format small decimals
      if (Math.abs(value) < 1 && value !== 0) {
        return value.toFixed(4)
      }
      return value.toFixed(2)
    }
    return String(value)
  }

  return (
    <div className="indicators-panel">
      <h2>Indicadores Clave</h2>
      {Object.keys(indicators).length > 0 ? (
        <div className="indicators-grid">
          {Object.entries(indicators).map(([key, value]) => (
            <div key={key} className="indicator-item">
              <span className="indicator-label">{key.replace(/_/g, ' ')}</span>
              <span className="indicator-value">{formatValue(key, value)}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="empty">No hay indicadores disponibles</div>
      )}
      {Object.keys(riskMetrics).length > 0 && (
        <div className="risk-metrics">
          <h3>Métricas de Riesgo</h3>
          <div className="indicators-grid">
            {Object.entries(riskMetrics).map(([key, value]) => (
              <div key={key} className="indicator-item">
                <span className="indicator-label">{key.replace(/_/g, ' ')}</span>
                <span className="indicator-value">{formatValue(key, value)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default IndicatorsPanel

