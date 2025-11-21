import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { api, isTimeoutError, getErrorMessage } from '../api/hooks'
import { ContextualArticles } from './ContextualArticle'
import './UserRiskPanel.css'

interface Warning {
  type: string
  severity: 'warning' | 'critical'
  message: string
}

interface UserRiskState {
  status: string
  user_id: string
  current_drawdown_pct: number
  longest_losing_streak: number
  current_losing_streak: number
  longest_winning_streak: number
  current_winning_streak: number
  trades_last_24h: number
  avg_exposure_pct: number
  cooldown_until: string | null
  cooldown_reason: string | null
  is_on_cooldown: boolean
  cooldown_remaining_seconds: number | null
  current_equity: number
  total_notional: number
  effective_leverage: number
  leverage_hard_stop: boolean
  leverage_hard_stop_since: string | null
  last_updated: string | null
  warnings: Warning[]
  contextual_articles?: ContextualArticle[]
}

interface ContextualArticle {
  id: number
  title: string
  slug: string
  summary: string
  category: string
}

interface UserRiskPanelProps {
  userId?: string
  pollingInterval?: number | false
}

export function UserRiskPanel({ userId = '00000000-0000-0000-0000-000000000001', pollingInterval = 30000 }: UserRiskPanelProps) {
  const { data, isLoading, error } = useQuery<UserRiskState>({
    queryKey: ['user-risk-state', userId],
    queryFn: async ({ signal }) => {
      const { data } = await api.get(`/api/v1/user-risk/state?user_id=${userId}`, { signal })
      return data
    },
    refetchInterval: pollingInterval,
    staleTime: 10000,
  })

  const criticalWarnings = useMemo(() => {
    return data?.warnings?.filter(w => w.severity === 'critical') || []
  }, [data?.warnings])

  const warningWarnings = useMemo(() => {
    return data?.warnings?.filter(w => w.severity === 'warning') || []
  }, [data?.warnings])

  if (isLoading) {
    return (
      <div className="user-risk-panel loading">
        <div className="loading-spinner">Cargando estado de riesgo...</div>
      </div>
    )
  }

  if (error) {
    const isTimeout = isTimeoutError(error)
    const errorMessage = getErrorMessage(error)
    return (
      <div className="user-risk-panel error">
        {isTimeout ? (
          <>
            <p><strong>⏱️ Tiempo de espera excedido</strong></p>
            <p>El backend está ocupado procesando la solicitud. Por favor, intenta nuevamente en unos momentos.</p>
          </>
        ) : (
          <>
            <p><strong>❌ Error al cargar estado de riesgo</strong></p>
            <p>{errorMessage}</p>
          </>
        )}
      </div>
    )
  }

  if (!data) {
    return null
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

  return (
    <div className="user-risk-panel">
      <h3 className="panel-title">Estado Psicológico de Riesgo</h3>
      
      {data.is_on_cooldown && data.cooldown_remaining_seconds !== null && (
        <div className="cooldown-banner">
          <div className="cooldown-icon">⏸️</div>
          <div className="cooldown-content">
            <h4 className="cooldown-title">Período de Enfriamiento Activo</h4>
            <p className="cooldown-reason">{data.cooldown_reason || "Operaciones bloqueadas temporalmente"}</p>
            <p className="cooldown-time">
              Tiempo restante: <strong>{formatTimeRemaining(data.cooldown_remaining_seconds)}</strong>
            </p>
            {data.cooldown_until && (
              <p className="cooldown-until">
                Hasta: {new Date(data.cooldown_until).toLocaleString('es-ES')}
              </p>
            )}
          </div>
        </div>
      )}
      
      {(criticalWarnings.length > 0 || warningWarnings.length > 0) && (
        <div className="warnings-section">
          {criticalWarnings.length > 0 && (
            <div className="warnings critical">
              <h4 className="warnings-title critical">⚠️ Alertas Críticas</h4>
              {criticalWarnings.map((warning, idx) => (
                <div key={idx} className="warning-item critical">
                  {warning.message}
                </div>
              ))}
            </div>
          )}
          
          {warningWarnings.length > 0 && (
            <div className="warnings warning">
              <h4 className="warnings-title warning">⚠️ Advertencias</h4>
              {warningWarnings.map((warning, idx) => (
                <div key={idx} className="warning-item warning">
                  {warning.message}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="metrics-grid">
        <div className="metric-card">
          <div className="metric-label">Drawdown Actual</div>
          <div className={`metric-value ${data.current_drawdown_pct >= 15.0 ? 'danger' : data.current_drawdown_pct >= 10.0 ? 'warning' : 'normal'}`}>
            {data.current_drawdown_pct.toFixed(2)}%
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Racha Perdedora Actual</div>
          <div className={`metric-value ${data.current_losing_streak >= 5 ? 'danger' : data.current_losing_streak >= 3 ? 'warning' : 'normal'}`}>
            {data.current_losing_streak}
          </div>
          <div className="metric-subtitle">Máxima: {data.longest_losing_streak}</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Racha Ganadora Actual</div>
          <div className={`metric-value ${data.current_winning_streak >= 5 ? 'success' : 'normal'}`}>
            {data.current_winning_streak}
          </div>
          <div className="metric-subtitle">Máxima: {data.longest_winning_streak}</div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Trades Últimas 24h</div>
          <div className={`metric-value ${data.trades_last_24h >= 20 ? 'danger' : data.trades_last_24h >= 10 ? 'warning' : 'normal'}`}>
            {data.trades_last_24h}
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Exposición Promedio</div>
          <div className="metric-value normal">
            {data.avg_exposure_pct.toFixed(2)}%
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Apalancamiento Efectivo</div>
          <div className={`metric-value ${data.effective_leverage >= 3.0 ? 'danger' : data.effective_leverage >= 2.0 ? 'warning' : 'normal'}`}>
            {data.effective_leverage.toFixed(2)}×
          </div>
          <div className="metric-subtitle">
            Equity: ${data.current_equity.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>

        <div className="metric-card">
          <div className="metric-label">Valor Nominal Total</div>
          <div className="metric-value normal">
            ${data.total_notional.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
      </div>
      
      {data.leverage_hard_stop && (
        <div className="leverage-hard-stop-banner">
          <div className="hard-stop-icon">🛑</div>
          <div className="hard-stop-content">
            <h4 className="hard-stop-title">Hard Stop Activo: Apalancamiento Excesivo</h4>
            <p className="hard-stop-message">
              El apalancamiento efectivo ({data.effective_leverage.toFixed(2)}×) excede el umbral de seguridad (3×).
              Reduzca la exposición antes de continuar operando.
            </p>
            {data.leverage_hard_stop_since && (
              <p className="hard-stop-since">
                Activo desde: {new Date(data.leverage_hard_stop_since).toLocaleString('es-ES')}
              </p>
            )}
          </div>
        </div>
      )}

      {data.last_updated && (
        <div className="last-updated">
          Última actualización: {new Date(data.last_updated).toLocaleString('es-ES')}
        </div>
      )}

      {data.contextual_articles && data.contextual_articles.length > 0 && (
        <ContextualArticles articles={data.contextual_articles} userId={userId} />
      )}
    </div>
  )
}

export default UserRiskPanel

