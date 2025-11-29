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
  const backtestMetricsSource = (safeRisk as any)?.backtest_metrics_source
  const backtestMetricsStatus = (safeRisk as any)?.backtest_metrics_status
  const backtestNoTrades = (safeRisk as any)?.backtest_no_trades === true
  const backtestNoTradesRootCause = (safeRisk as any)?.backtest_no_trades_root_cause
  const showDegradedBanner = error && data && ((data as any).metadata?.served_from_cache || isDevFallback || backtestMetricsSource === 'fallback')
  
  // Determine if metrics are from fallback or demo
  const isMetricsFallback = backtestMetricsSource === 'fallback' || backtestMetricsStatus === 'NO_TRADES' || backtestNoTrades
  const isMetricsDemo = isDevFallback && !backtestMetricsSource
  
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
      {isMetricsFallback && !showDegradedBanner && (
        <div style={{
          padding: '0.75rem',
          backgroundColor: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: '0.5rem',
          marginBottom: '1rem',
          fontSize: '0.875rem',
        }}>
          <p style={{ margin: 0, color: '#ef4444', fontWeight: 600 }}>
            ⚠️ Métricas de riesgo basadas en backtest fallido
          </p>
          {backtestNoTradesRootCause && (
            <p style={{ margin: '0.5rem 0 0 0', color: 'rgba(255, 255, 255, 0.8)', fontSize: '0.75rem' }}>
              Causa: {backtestNoTradesRootCause === 'invalid_stop_loss' ? 'Stop loss inválido' :
                      backtestNoTradesRootCause === 'enter_signals_zero_size' ? 'Tamaño de posición cero' :
                      backtestNoTradesRootCause === 'orders_rejected' ? 'Órdenes rechazadas' :
                      backtestNoTradesRootCause === 'no_signals_generated' ? 'Sin señales generadas' :
                      backtestNoTradesRootCause === 'no_enter_signals' ? 'Sin señales de entrada' :
                      'Causa desconocida'}
            </p>
          )}
        </div>
      )}
      {isMetricsDemo && !showDegradedBanner && !isMetricsFallback && (
        <div style={{
          padding: '0.75rem',
          backgroundColor: 'rgba(147, 51, 234, 0.1)',
          border: '1px solid rgba(147, 51, 234, 0.3)',
          borderRadius: '0.5rem',
          marginBottom: '1rem',
          fontSize: '0.875rem',
        }}>
          <p style={{ margin: 0, color: '#9333ea', fontWeight: 600 }}>
            🔧 Métricas de riesgo en modo desarrollo
          </p>
          <p style={{ margin: '0.5rem 0 0 0', color: 'rgba(255, 255, 255, 0.8)', fontSize: '0.75rem' }}>
            Los valores mostrados son de respaldo y no reflejan resultados reales de backtesting.
          </p>
        </div>
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


