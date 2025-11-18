import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import './ObservabilityDashboard.css'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const api = axios.create({ baseURL: API_BASE_URL, headers: { 'Content-Type': 'application/json' } })

interface MetricValue {
  value: number
  threshold: number
  status: 'good' | 'warning' | 'critical'
  degradation_pct?: number
}

interface DashboardMetrics {
  rolling_sharpe_7d?: number
  rolling_sharpe_30d?: number
  rolling_sharpe_90d?: number
  hit_rate_7d?: number
  hit_rate_30d?: number
  hit_rate_90d?: number
  max_drawdown_7d?: number
  max_drawdown_30d?: number
  max_drawdown_90d?: number
  equity_slope?: number
  tracking_error_mean?: number
  tracking_error_correlation?: number
  current_drawdown_pct?: number
  fill_rate?: number
  [key: string]: number | undefined
}

interface Alert {
  metric: string
  current_value: number
  threshold: number
  degradation_pct?: number
  severity: 'warning' | 'critical'
  type: string
  message: string
}

interface DashboardResponse {
  status: string
  metrics: DashboardMetrics
  thresholds: Record<string, number>
  alerts: Alert[]
  alerts_count: number
  timestamp: string
}

const useObservabilityDashboard = (isPrivate: boolean = false) => {
  return useQuery({
    queryKey: ['observability', 'dashboard', isPrivate],
    queryFn: async () => {
      const endpoint = isPrivate ? '/api/v1/observability/private/dashboard' : '/api/v1/observability/public/dashboard'
      const { data } = await api.get<DashboardResponse>(endpoint)
      return data
    },
    refetchInterval: 30000, // Poll every 30 seconds
    staleTime: 10000,
  })
}

export function ObservabilityDashboard({ isPrivate = false }: { isPrivate?: boolean }) {
  const [showThresholds, setShowThresholds] = useState(true)
  const { data, isLoading, isError } = useObservabilityDashboard(isPrivate)

  const metricsDisplay = useMemo(() => {
    if (!data) return {}

    const display: Record<string, MetricValue> = {}
    const metrics = data.metrics
    const thresholds = data.thresholds

    // Process each metric
    for (const [metricName, threshold] of Object.entries(thresholds)) {
      const currentValue = metrics[metricName]
      if (currentValue === undefined) continue

      const isHigherBetter = metricName.includes('sharpe') || metricName.includes('hit_rate') || 
                            metricName.includes('correlation') || metricName.includes('fill_rate') ||
                            metricName.includes('equity_slope')

      let status: 'good' | 'warning' | 'critical' = 'good'
      let degradation_pct = 0

      if (isHigherBetter) {
        if (currentValue < threshold) {
          degradation_pct = threshold > 0 ? ((threshold - currentValue) / threshold) * 100 : 100
          status = degradation_pct > 40 ? 'critical' : 'warning'
        }
      } else {
        if (currentValue > threshold) {
          degradation_pct = threshold > 0 ? ((currentValue - threshold) / threshold) * 100 : 100
          status = degradation_pct > 40 ? 'critical' : 'warning'
        }
      }

      display[metricName] = {
        value: currentValue,
        threshold,
        status,
        degradation_pct,
      }
    }

    return display
  }, [data])

  if (isLoading) {
    return (
      <section className="observability-dashboard" aria-busy="true">
        <header>
          <h2>Dashboard de Observabilidad</h2>
        </header>
        <p>Cargando métricas...</p>
      </section>
    )
  }

  if (isError || !data) {
    return (
      <section className="observability-dashboard" aria-live="polite">
        <header>
          <h2>Dashboard de Observabilidad</h2>
        </header>
        <p>Error al cargar métricas. Por favor, intente nuevamente.</p>
      </section>
    )
  }

  const criticalAlerts = data.alerts.filter(a => a.severity === 'critical')
  const warningAlerts = data.alerts.filter(a => a.severity === 'warning')

  return (
    <section className="observability-dashboard">
      <header>
        <div className="dashboard-header-row">
          <h2>Dashboard de Observabilidad {isPrivate && '(Privado)'}</h2>
          <div className="dashboard-actions">
            <label className="thresholds-toggle">
              <input
                type="checkbox"
                checked={showThresholds}
                onChange={(e) => setShowThresholds(e.target.checked)}
              />
              <span>Mostrar umbrales</span>
            </label>
            <span className="last-update">
              Última actualización: {new Date(data.timestamp).toLocaleTimeString()}
            </span>
          </div>
        </div>

        {data.alerts_count > 0 && (
          <div className={`alerts-summary ${criticalAlerts.length > 0 ? 'has-critical' : ''}`}>
            <div className="alert-count critical">
              🔴 {criticalAlerts.length} Críticas
            </div>
            <div className="alert-count warning">
              🟡 {warningAlerts.length} Advertencias
            </div>
          </div>
        )}
      </header>

      {data.alerts_count > 0 && (
        <div className="alerts-section">
          {criticalAlerts.length > 0 && (
            <div className="alerts-list critical">
              <h3>Alertas Críticas</h3>
              {criticalAlerts.map((alert, idx) => (
                <div key={idx} className="alert-item">
                  <div className="alert-metric">{alert.metric}</div>
                  <div className="alert-details">
                    <span className="alert-value">Valor: {alert.current_value.toFixed(2)}</span>
                    <span className="alert-threshold">Umbral: {alert.threshold.toFixed(2)}</span>
                    {alert.degradation_pct !== undefined && (
                      <span className="alert-degradation">
                        Degradación: {alert.degradation_pct.toFixed(1)}%
                      </span>
                    )}
                  </div>
                  <div className="alert-message">{alert.message}</div>
                </div>
              ))}
            </div>
          )}

          {warningAlerts.length > 0 && (
            <div className="alerts-list warning">
              <h3>Advertencias</h3>
              {warningAlerts.map((alert, idx) => (
                <div key={idx} className="alert-item">
                  <div className="alert-metric">{alert.metric}</div>
                  <div className="alert-details">
                    <span className="alert-value">Valor: {alert.current_value.toFixed(2)}</span>
                    <span className="alert-threshold">Umbral: {alert.threshold.toFixed(2)}</span>
                    {alert.degradation_pct !== undefined && (
                      <span className="alert-degradation">
                        Degradación: {alert.degradation_pct.toFixed(1)}%
                      </span>
                    )}
                  </div>
                  <div className="alert-message">{alert.message}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="metrics-grid">
        {/* Rolling Sharpe */}
        <div className="metric-category">
          <h3>Rolling Sharpe Ratio</h3>
          {['7d', '30d', '90d'].map(horizon => {
            const key = `rolling_sharpe_${horizon}` as keyof DashboardMetrics
            const metric = metricsDisplay[key]
            if (!metric) return null

            return (
              <div key={horizon} className={`metric-card ${metric.status}`}>
                <div className="metric-label">{horizon}</div>
                <div className="metric-value">{metric.value.toFixed(2)}</div>
                {showThresholds && (
                  <div className="metric-threshold">Umbral: {metric.threshold.toFixed(2)}</div>
                )}
                {metric.degradation_pct !== undefined && metric.degradation_pct > 0 && (
                  <div className="metric-degradation">
                    Degradación: {metric.degradation_pct.toFixed(1)}%
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Hit Rate */}
        <div className="metric-category">
          <h3>Hit Rate (%)</h3>
          {['7d', '30d', '90d'].map(horizon => {
            const key = `hit_rate_${horizon}` as keyof DashboardMetrics
            const metric = metricsDisplay[key]
            if (!metric) return null

            return (
              <div key={horizon} className={`metric-card ${metric.status}`}>
                <div className="metric-label">{horizon}</div>
                <div className="metric-value">{metric.value.toFixed(1)}%</div>
                {showThresholds && (
                  <div className="metric-threshold">Umbral: {metric.threshold.toFixed(1)}%</div>
                )}
                {metric.degradation_pct !== undefined && metric.degradation_pct > 0 && (
                  <div className="metric-degradation">
                    Degradación: {metric.degradation_pct.toFixed(1)}%
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Max Drawdown */}
        <div className="metric-category">
          <h3>Max Drawdown (%)</h3>
          {['7d', '30d', '90d'].map(horizon => {
            const key = `max_drawdown_${horizon}` as keyof DashboardMetrics
            const metric = metricsDisplay[key]
            if (!metric) return null

            return (
              <div key={horizon} className={`metric-card ${metric.status}`}>
                <div className="metric-label">{horizon}</div>
                <div className="metric-value">{metric.value.toFixed(2)}%</div>
                {showThresholds && (
                  <div className="metric-threshold">Umbral: {metric.threshold.toFixed(1)}%</div>
                )}
                {metric.degradation_pct !== undefined && metric.degradation_pct > 0 && (
                  <div className="metric-degradation">
                    Degradación: {metric.degradation_pct.toFixed(1)}%
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {/* Other Metrics */}
        <div className="metric-category">
          <h3>Métricas Adicionales</h3>

          {metricsDisplay.equity_slope && (
            <div className={`metric-card ${metricsDisplay.equity_slope.status}`}>
              <div className="metric-label">Equity Slope (bps/day)</div>
              <div className="metric-value">{metricsDisplay.equity_slope.value.toFixed(2)}</div>
              {showThresholds && (
                <div className="metric-threshold">Umbral: {metricsDisplay.equity_slope.threshold.toFixed(1)}</div>
              )}
            </div>
          )}

          {metricsDisplay.tracking_error_mean !== undefined && (
            <div className={`metric-card ${metricsDisplay.tracking_error_mean.status}`}>
              <div className="metric-label">Tracking Error (mean)</div>
              <div className="metric-value">{(metricsDisplay.tracking_error_mean.value * 100).toFixed(2)}%</div>
              {showThresholds && (
                <div className="metric-threshold">
                  Umbral: {(metricsDisplay.tracking_error_mean.threshold * 100).toFixed(1)}%
                </div>
              )}
            </div>
          )}

          {metricsDisplay.tracking_error_correlation !== undefined && (
            <div className={`metric-card ${metricsDisplay.tracking_error_correlation.status}`}>
              <div className="metric-label">Tracking Error (correlation)</div>
              <div className="metric-value">{(metricsDisplay.tracking_error_correlation.value * 100).toFixed(1)}%</div>
              {showThresholds && (
                <div className="metric-threshold">
                  Umbral: {(metricsDisplay.tracking_error_correlation.threshold * 100).toFixed(1)}%
                </div>
              )}
            </div>
          )}

          {metricsDisplay.current_drawdown_pct !== undefined && (
            <div className={`metric-card ${
              metricsDisplay.current_drawdown_pct.value > 20 ? 'critical' :
              metricsDisplay.current_drawdown_pct.value > 10 ? 'warning' : 'good'
            }`}>
              <div className="metric-label">Drawdown Actual</div>
              <div className="metric-value">{metricsDisplay.current_drawdown_pct.value.toFixed(2)}%</div>
              {showThresholds && (
                <div className="metric-threshold">
                  Umbral: {metricsDisplay.current_drawdown_pct.threshold.toFixed(1)}%
                </div>
              )}
            </div>
          )}

          {metricsDisplay.fill_rate !== undefined && (
            <div className={`metric-card ${metricsDisplay.fill_rate.status}`}>
              <div className="metric-label">Fill Rate</div>
              <div className="metric-value">{(metricsDisplay.fill_rate.value * 100).toFixed(1)}%</div>
              {showThresholds && (
                <div className="metric-threshold">
                  Umbral: {(metricsDisplay.fill_rate.threshold * 100).toFixed(1)}%
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

export default ObservabilityDashboard




