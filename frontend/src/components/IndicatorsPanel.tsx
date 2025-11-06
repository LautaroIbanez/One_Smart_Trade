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

  return (
    <div className="indicators-panel">
      <h2>Indicadores Clave</h2>
      <div className="indicators-grid">
        {Object.entries(indicators).map(([key, value]) => (
          <div key={key} className="indicator-item">
            <span className="indicator-label">{key}</span>
            <span className="indicator-value">{String(value)}</span>
          </div>
        ))}
      </div>
      <div className="risk-metrics">
        <h3>Métricas de Riesgo</h3>
        <div className="indicators-grid">
          {Object.entries(riskMetrics).map(([key, value]) => (
            <div key={key} className="indicator-item">
              <span className="indicator-label">{key}</span>
              <span className="indicator-value">{String(value)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default IndicatorsPanel

