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

  if (!risk) {
    return (
      <div className="risk-panel">
        <h2>Riesgo</h2>
        <div className="empty-state">
          <p>No hay métricas de riesgo disponibles</p>
        </div>
      </div>
    )
  }

  const showDegradedBanner = error && data && (data as any).metadata?.served_from_cache
  const items = [
    { label: 'RR', value: risk.risk_reward_ratio },
    { label: 'Prob. SL', value: `${risk.sl_probability}%` },
    { label: 'Prob. TP', value: `${risk.tp_probability}%` },
    { label: 'Drawdown esp.', value: risk.expected_drawdown },
    { label: 'Volatilidad', value: `${risk.volatility}%` },
  ]
  return (
    <div className="risk-panel">
      <h2>Riesgo</h2>
      {showDegradedBanner && (
        <DegradedDataBanner 
          message="Mostrando métricas de riesgo desde caché."
          source={(data as any).metadata?.source}
          cachedAt={(data as any).metadata?.generated_at}
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


