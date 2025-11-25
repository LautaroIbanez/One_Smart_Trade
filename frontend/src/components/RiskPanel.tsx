import { ErrorState } from './shared/ErrorState'
import { LoadingState } from './shared/LoadingState'
import { DegradedDataBanner } from './shared/DegradedDataBanner'
import { useTodayRecommendation } from '../api/hooks'
import './RiskPanel.css'

type Props = { risk: Record<string, unknown> | undefined }

export default function RiskPanel({ risk }: Props) {
  const { isLoading, error, data, refetch } = useTodayRecommendation()
  
  if (isLoading && !risk) {
    return (
      <div className="risk-panel">
        <h2>Riesgo</h2>
        <LoadingState message="Cargando métricas de riesgo..." compact />
      </div>
    )
  }

  if (error && !risk) {
    return (
      <div className="risk-panel">
        <h2>Riesgo</h2>
        <ErrorState 
          error={error} 
          title="Error al cargar métricas de riesgo"
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  // Provide safe defaults if risk is null/undefined
  const safeRisk = risk || {
    risk_reward_ratio: 0,
    sl_probability: 0,
    tp_probability: 0,
    expected_drawdown: 0,
    volatility: 0,
    dev_fallback: true,
    degraded_mode: true,
  }

  const isDevFallback = (safeRisk as any)?.dev_fallback === true || (safeRisk as any)?.degraded_mode === true
  const showDegradedBanner = error && data && ((data as any).metadata?.served_from_cache || isDevFallback)
  const items = [
    { label: 'RR', value: safeRisk.risk_reward_ratio ?? 0 },
    { label: 'Prob. SL', value: `${safeRisk.sl_probability ?? 0}%` },
    { label: 'Prob. TP', value: `${safeRisk.tp_probability ?? 0}%` },
    { label: 'Drawdown esp.', value: safeRisk.expected_drawdown ?? 0 },
    { label: 'Volatilidad', value: `${safeRisk.volatility ?? 0}%` },
  ]
  return (
    <div className="risk-panel">
      <h2>Riesgo</h2>
      {showDegradedBanner && (
        <DegradedDataBanner 
          message={isDevFallback ? "Modo desarrollo: Métricas de riesgo de respaldo generadas automáticamente." : "Mostrando métricas de riesgo desde caché."}
          source={(data as any)?.metadata?.source}
          cachedAt={(data as any)?.metadata?.generated_at}
        />
      )}
      <div className="risk-grid">
        {items.map((it) => (
          <div key={it.label} className="risk-item">
            <span className="risk-label">{it.label}</span>
            <span className="risk-value">{String(it.value)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}


