import { useTodayRecommendation } from '../api/hooks'
import { ErrorState } from './shared/ErrorState'
import { LoadingState } from './shared/LoadingState'
import { DegradedDataBanner } from './shared/DegradedDataBanner'
import './IndicatorsPanel.css'

function IndicatorsPanel() {
  const { data, isLoading, error, refetch } = useTodayRecommendation()

  if (isLoading && !data) {
    return (
      <div className="indicators-panel" role="status" aria-live="polite">
        <h2>Indicadores Clave</h2>
        <LoadingState message="Cargando indicadores..." compact />
      </div>
    )
  }

  if (error && !data) {
    return (
      <div className="indicators-panel" role="alert">
        <h2>Indicadores Clave</h2>
        <ErrorState 
          error={error} 
          title="Error al cargar indicadores"
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  // Provide safe defaults if data is null/undefined
  const safeData = data || {
    indicators: {},
    risk_metrics: { dev_fallback: true, degraded_mode: true },
  }

  const indicators = safeData.indicators || {}
  const riskMetrics = safeData.risk_metrics || {}

  // Format indicator values for display
  const formatValue = (key: string, value: unknown): string => {
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

  const hasIndicators = Object.keys(indicators).length > 0
  const hasRiskMetrics = Object.keys(riskMetrics).length > 0
  const isDevFallback = (safeData as any)?.dev_fallback === true || (riskMetrics as any)?.dev_fallback === true
  const showDegradedBanner = error && safeData && ((safeData as any).metadata?.served_from_cache || isDevFallback)

  return (
    <div className="indicators-panel">
      <h2>Indicadores Clave</h2>
      {showDegradedBanner && (
        <DegradedDataBanner 
          message={isDevFallback ? "Modo desarrollo: Indicadores de respaldo generados automáticamente." : "Mostrando indicadores desde caché."}
          source={(safeData as any).metadata?.source}
          cachedAt={(safeData as any).metadata?.generated_at}
        />
      )}
      {hasIndicators ? (
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
      {hasRiskMetrics && (
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
      {error && !hasIndicators && !hasRiskMetrics && (
        <ErrorState 
          error={error} 
          title="Error al cargar indicadores"
          onRetry={() => refetch()}
        />
      )}
    </div>
  )
}

export default IndicatorsPanel

