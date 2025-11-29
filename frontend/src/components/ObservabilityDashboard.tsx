import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, usePerformanceSummary } from '../api/hooks'
import { getPollingInterval } from '../utils/polling'
import './ObservabilityDashboard.css'

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
    queryFn: async ({ signal }) => {
      const endpoint = isPrivate ? '/api/v1/observability/private/dashboard' : '/api/v1/observability/public/dashboard'
      const { data } = await api.get<DashboardResponse>(endpoint, { signal })
      return data
    },
    staleTime: 300_000, // 5 minutes - increased from 10s
    refetchInterval: (query) => {
      const data = query.state.data as DashboardResponse | undefined
      const status = data?.status
      const isStale = query.isStale()
      const cacheAge = query.state.dataUpdatedAt ? Date.now() - query.state.dataUpdatedAt : undefined
      
      return getPollingInterval(status, isStale, cacheAge)
    },
  })
}

export function ObservabilityDashboard({ isPrivate = false }: { isPrivate?: boolean }) {
  const [showThresholds, setShowThresholds] = useState(true)
  const { data, isLoading, isError } = useObservabilityDashboard(isPrivate)
  const { data: performanceData } = usePerformanceSummary()

  // Normalize response data to handle partial responses safely
  const normalizedData = useMemo(() => {
    if (!data) return null

    // Check for processing status or incomplete data
    if (data.status === 'processing' || data.status === 'pending') {
      return { ...data, isProcessing: true }
    }

    // Normalize all potentially missing fields with safe defaults
    const alerts = Array.isArray(data?.alerts) ? data.alerts : []
    const thresholds = data?.thresholds ?? {}
    const metrics = data?.metrics ?? {}
    const alertsCount = typeof data?.alerts_count === 'number' ? data.alerts_count : alerts.length
    const timestamp = data?.timestamp ?? new Date().toISOString()

    return {
      ...data,
      alerts,
      thresholds,
      metrics,
      alerts_count: alertsCount,
      timestamp,
      isProcessing: false,
    }
  }, [data])

  const metricsDisplay = useMemo(() => {
    if (!normalizedData || normalizedData.isProcessing) return {}

    const display: Record<string, MetricValue> = {}
    const metrics = normalizedData.metrics
    const thresholds = normalizedData.thresholds

    // Process each metric - thresholds is guaranteed to be an object (empty if missing)
    for (const [metricName, threshold] of Object.entries(thresholds)) {
      const currentValue = metrics[metricName]
      if (currentValue === undefined || typeof threshold !== 'number') continue

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
  }, [normalizedData])

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

  if (isError || !normalizedData) {
    return (
      <section className="observability-dashboard" aria-live="polite">
        <header>
          <h2>Dashboard de Observabilidad</h2>
        </header>
        <p>Error al cargar métricas. Por favor, intente nuevamente.</p>
      </section>
    )
  }

  // Early fallback for processing status or missing critical fields
  if (normalizedData.isProcessing || (!normalizedData.metrics || Object.keys(normalizedData.metrics).length === 0)) {
    return (
      <section className="observability-dashboard" aria-live="polite">
        <header>
          <h2>Dashboard de Observabilidad {isPrivate && '(Privado)'}</h2>
        </header>
        <div className="observability-status-message">
          <p>
            {normalizedData.isProcessing 
              ? 'El servicio de observabilidad está procesando datos. Por favor, espera unos momentos.'
              : 'Los datos de métricas aún no están disponibles. El servicio puede estar inicializándose.'}
          </p>
          <p className="status-hint">
            Los datos se actualizarán automáticamente en breve.
          </p>
        </div>
      </section>
    )
  }

  // Safe array filtering - alerts is guaranteed to be an array (empty if missing)
  const criticalAlerts = normalizedData.alerts.filter(a => a?.severity === 'critical')
  const warningAlerts = normalizedData.alerts.filter(a => a?.severity === 'warning')

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
              Última actualización: {new Date(normalizedData.timestamp).toLocaleTimeString()}
            </span>
          </div>
        </div>

        {normalizedData.alerts_count > 0 && (
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

      {normalizedData.alerts_count > 0 && (
        <div className="alerts-section">
          {criticalAlerts.length > 0 && (
            <div className="alerts-list critical">
              <h3>Alertas Críticas</h3>
              {criticalAlerts.map((alert, idx) => (
                <div key={idx} className="alert-item">
                  <div className="alert-metric">{alert?.metric ?? 'Métrica desconocida'}</div>
                  <div className="alert-details">
                    {typeof alert?.current_value === 'number' && (
                      <span className="alert-value">Valor: {alert.current_value.toFixed(2)}</span>
                    )}
                    {typeof alert?.threshold === 'number' && (
                      <span className="alert-threshold">Umbral: {alert.threshold.toFixed(2)}</span>
                    )}
                    {typeof alert?.degradation_pct === 'number' && (
                      <span className="alert-degradation">
                        Degradación: {alert.degradation_pct.toFixed(1)}%
                      </span>
                    )}
                  </div>
                  {alert?.message && (
                    <div className="alert-message">{alert.message}</div>
                  )}
                </div>
              ))}
            </div>
          )}

          {warningAlerts.length > 0 && (
            <div className="alerts-list warning">
              <h3>Advertencias</h3>
              {warningAlerts.map((alert, idx) => (
                <div key={idx} className="alert-item">
                  <div className="alert-metric">{alert?.metric ?? 'Métrica desconocida'}</div>
                  <div className="alert-details">
                    {typeof alert?.current_value === 'number' && (
                      <span className="alert-value">Valor: {alert.current_value.toFixed(2)}</span>
                    )}
                    {typeof alert?.threshold === 'number' && (
                      <span className="alert-threshold">Umbral: {alert.threshold.toFixed(2)}</span>
                    )}
                    {typeof alert?.degradation_pct === 'number' && (
                      <span className="alert-degradation">
                        Degradación: {alert.degradation_pct.toFixed(1)}%
                      </span>
                    )}
                  </div>
                  {alert?.message && (
                    <div className="alert-message">{alert.message}</div>
                  )}
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

      {/* Freshness Status Section */}
      {normalizedData && (normalizedData as any).freshness_status && (
        <div className="freshness-status-section" style={{
          marginTop: '2rem',
          padding: '1.5rem',
          backgroundColor: 'rgba(59, 130, 246, 0.1)',
          border: '1px solid rgba(59, 130, 246, 0.3)',
          borderRadius: '0.5rem',
        }}>
          <h3 style={{ margin: '0 0 1rem 0', color: '#3b82f6', fontSize: '1.125rem' }}>
            📊 Estado de Frescura de Datos
          </h3>
          {(() => {
            const freshness = (normalizedData as any).freshness_status
            const intervals = freshness?.intervals || {}
            const staleCounts = freshness?.stale_counts || {}
            const noTradesCounts = (normalizedData as any).no_trades_counts || {}
            const totalNoTrades = (normalizedData as any).total_no_trades || 0
            
            return (
              <div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
                  {Object.entries(intervals).map(([interval, status]: [string, any]) => (
                    <div key={interval} style={{ 
                      padding: '0.75rem', 
                      backgroundColor: status.is_stale ? 'rgba(239, 68, 68, 0.2)' : 'rgba(0, 0, 0, 0.2)', 
                      borderRadius: '0.375rem',
                      border: status.is_stale ? '1px solid rgba(239, 68, 68, 0.5)' : '1px solid rgba(255, 255, 255, 0.1)',
                    }}>
                      <div style={{ fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.7)', marginBottom: '0.25rem' }}>
                        {interval.toUpperCase()}
                      </div>
                      <div style={{ fontSize: '1rem', fontWeight: 600, color: status.is_stale ? '#ef4444' : '#22c55e' }}>
                        {status.is_stale ? '⚠️ Stale' : '✓ Fresh'}
                      </div>
                      {status.age_minutes !== undefined && (
                        <div style={{ fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.7)', marginTop: '0.25rem' }}>
                          {status.age_minutes.toFixed(1)} min old
                        </div>
                      )}
                      {staleCounts[interval] !== undefined && (
                        <div style={{ fontSize: '0.75rem', color: '#f97316', marginTop: '0.25rem' }}>
                          {staleCounts[interval]} stale warnings
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                
                {totalNoTrades > 0 && (
                  <div style={{ 
                    marginTop: '1rem',
                    padding: '0.75rem', 
                    backgroundColor: 'rgba(239, 68, 68, 0.15)', 
                    borderRadius: '0.375rem',
                  }}>
                    <div style={{ fontSize: '0.875rem', fontWeight: 500, color: '#ef4444', marginBottom: '0.5rem' }}>
                      ⚠️ NO_TRADES Events: {totalNoTrades} total
                    </div>
                    {Object.entries(noTradesCounts).length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                        {Object.entries(noTradesCounts).map(([cause, count]: [string, any]) => (
                          <span key={cause} style={{ 
                            padding: '0.25rem 0.5rem', 
                            backgroundColor: 'rgba(239, 68, 68, 0.2)', 
                            borderRadius: '0.25rem',
                            fontSize: '0.75rem',
                          }}>
                            {cause}: {count}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })()}
        </div>
      )}

      {/* Backtest Diagnostics Section */}
      {performanceData && (performanceData as any)?.metrics_status && (performanceData as any).metrics_status !== 'PASS' && (
        <div className="backtest-diagnostics-section" style={{
          marginTop: '2rem',
          padding: '1.5rem',
          backgroundColor: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: '0.5rem',
        }}>
          <h3 style={{ margin: '0 0 1rem 0', color: '#ef4444', fontSize: '1.125rem' }}>
            🔍 Diagnóstico de Backtest
          </h3>
          {(() => {
            const metricsStatus = (performanceData as any).metrics_status
            const signalCounts = (performanceData as any).signal_counts || {}
            const rejectedOrdersCount = (performanceData as any).rejected_orders_count || 0
            const tradeCount = (performanceData as any).metrics?.total_trades || (performanceData as any).trade_count || 0
            const enterSignals = signalCounts.enter || 0
            const rootCause = (performanceData as any).no_trade_root_cause || (performanceData as any).no_trade_diagnostics?.root_cause
            const noTradeDiagnostics = (performanceData as any).no_trade_diagnostics

            // Determine the issue type
            let issueType = 'unknown'
            let issueMessage = ''
            
            if (enterSignals === 0) {
              issueType = 'sin_señales'
              issueMessage = 'No se generaron señales de entrada durante el backtest'
            } else if (rejectedOrdersCount > 0) {
              issueType = 'órdenes_rechazadas'
              issueMessage = `${rejectedOrdersCount} órdenes fueron rechazadas por el simulador de ejecución`
            } else if (enterSignals > 0 && tradeCount === 0) {
              issueType = 'tamaño_cero'
              issueMessage = `${enterSignals} señales de entrada generadas pero tamaño de posición = 0`
            } else if (enterSignals > tradeCount) {
              issueType = 'conversión_parcial'
              issueMessage = `${enterSignals} señales de entrada generadas, ${tradeCount} trades ejecutados`
            }

            return (
              <div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
                  <div style={{ padding: '0.75rem', backgroundColor: 'rgba(0, 0, 0, 0.2)', borderRadius: '0.375rem' }}>
                    <div style={{ fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.7)', marginBottom: '0.25rem' }}>Señales de Entrada</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 600, color: '#fff' }}>{enterSignals}</div>
                  </div>
                  <div style={{ padding: '0.75rem', backgroundColor: 'rgba(0, 0, 0, 0.2)', borderRadius: '0.375rem' }}>
                    <div style={{ fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.7)', marginBottom: '0.25rem' }}>Trades Generados</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 600, color: '#fff' }}>{tradeCount}</div>
                  </div>
                  {rejectedOrdersCount > 0 && (
                    <div style={{ padding: '0.75rem', backgroundColor: 'rgba(239, 68, 68, 0.2)', borderRadius: '0.375rem' }}>
                      <div style={{ fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.7)', marginBottom: '0.25rem' }}>Órdenes Rechazadas</div>
                      <div style={{ fontSize: '1.25rem', fontWeight: 600, color: '#ef4444' }}>{rejectedOrdersCount}</div>
                    </div>
                  )}
                </div>
                
                {issueMessage && (
                  <div style={{ 
                    padding: '0.75rem', 
                    backgroundColor: 'rgba(239, 68, 68, 0.15)', 
                    borderRadius: '0.375rem',
                    marginBottom: '0.75rem',
                  }}>
                    <div style={{ fontSize: '0.875rem', color: '#ef4444', fontWeight: 500 }}>
                      ⚠️ {issueMessage}
                    </div>
                  </div>
                )}

                {rootCause && (
                  <div style={{ 
                    padding: '0.75rem', 
                    backgroundColor: 'rgba(0, 0, 0, 0.2)', 
                    borderRadius: '0.375rem',
                    marginBottom: '0.75rem',
                  }}>
                    <div style={{ fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.7)', marginBottom: '0.25rem' }}>Causa Raíz</div>
                    <div style={{ fontSize: '0.875rem', color: '#fff', fontWeight: 500 }}>
                      {rootCause === 'no_signals_generated' && '❌ No se generaron señales'}
                      {rootCause === 'no_enter_signals' && '❌ No se generaron señales de entrada'}
                      {rootCause === 'invalid_stop_loss' && '❌ Stop loss inválido (distancia = 0 o faltante)'}
                      {rootCause === 'enter_signals_zero_size' && '⚠️ Señales de entrada con tamaño cero'}
                      {rootCause === 'orders_rejected' && '⚠️ Órdenes rechazadas por simulador'}
                      {rootCause === 'unknown' && '❓ Causa desconocida'}
                      {!['no_signals_generated', 'no_enter_signals', 'invalid_stop_loss', 'enter_signals_zero_size', 'orders_rejected', 'unknown'].includes(rootCause) && rootCause}
                    </div>
                  </div>
                )}

                {noTradeDiagnostics?.reason && (
                  <div style={{ 
                    padding: '0.75rem', 
                    backgroundColor: 'rgba(0, 0, 0, 0.2)', 
                    borderRadius: '0.375rem',
                    fontSize: '0.875rem',
                    color: 'rgba(255, 255, 255, 0.9)',
                  }}>
                    <div style={{ fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.7)', marginBottom: '0.25rem' }}>Detalles</div>
                    <div>{noTradeDiagnostics.reason}</div>
                  </div>
                )}

                {signalCounts.total > 0 && (
                  <div style={{ 
                    marginTop: '0.75rem',
                    padding: '0.75rem', 
                    backgroundColor: 'rgba(0, 0, 0, 0.2)', 
                    borderRadius: '0.375rem',
                    fontSize: '0.75rem',
                    color: 'rgba(255, 255, 255, 0.7)',
                  }}>
                    <div style={{ marginBottom: '0.5rem', fontWeight: 500 }}>Desglose de Señales:</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                      {Object.entries(signalCounts).filter(([key, value]) => key !== 'total' && (value as number) > 0).map(([key, value]) => (
                        <span key={key} style={{ 
                          padding: '0.25rem 0.5rem', 
                          backgroundColor: 'rgba(255, 255, 255, 0.1)', 
                          borderRadius: '0.25rem',
                        }}>
                          {key}: {value as number}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )
          })()}
        </div>
      )}
    </section>
  )
}

export default ObservabilityDashboard






