import { useMemo } from 'react'
import { LineChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine } from 'recharts'
import { useSignalPerformance } from '../../api/hooks'
import './SignalCompliance.css'

const formatPercent = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
const formatPrice = (value: number) => value.toFixed(2)
const DEVIATION_THRESHOLD = 5.0 // Threshold for deviation badges (5%)

interface TrackingSeriesPoint {
  index: number
  theoretical: number
  realistic: number
  trackingError: number
}

function buildTrackingSeries(
  theoretical: number[] | undefined,
  realistic: number[] | undefined
): TrackingSeriesPoint[] {
  if (!theoretical || !realistic || theoretical.length === 0 || realistic.length === 0) {
    return []
  }
  
  const minLen = Math.min(theoretical.length, realistic.length)
  const series: TrackingSeriesPoint[] = []
  
  for (let i = 0; i < minLen; i++) {
    series.push({
      index: i,
      theoretical: theoretical[i] || 0,
      realistic: realistic[i] || 0,
      trackingError: (realistic[i] || 0) - (theoretical[i] || 0),
    })
  }
  
  return series
}

export function SignalCompliance() {
  const { data, isLoading, isError } = useSignalPerformance()

  const metrics = useMemo(() => {
    if (!data) {
      return {
        winRate: 0,
        trackingError: 0,
        trades: 0,
        lastEquity: 1,
        maxDrawdown: 0,
        meanDeviation: 0,
        p95Divergence: 0,
        maxDivergence: 0,
        correlation: 0,
        drawdownDivergence: 0,
      }
    }
    const lastEquity = data.equity_curve.length > 0 ? data.equity_curve[data.equity_curve.length - 1] : 1
    const maxDrawdown =
      data.drawdown_curve.length > 0
        ? Math.min(...data.drawdown_curve)
        : 0

    const trackingMetrics = data.tracking_error_metrics || {}
    const meanDeviation = trackingMetrics.mean_deviation || 0
    const p95Divergence = trackingMetrics.p95_divergence || 0
    const maxDivergence = trackingMetrics.max_divergence || 0
    const correlation = trackingMetrics.correlation || 0
    const drawdownDivergence = trackingMetrics.max_drawdown_divergence || 0

    return {
      winRate: data.win_rate,
      trackingError: data.average_tracking_error,
      trades: data.trades_evaluated,
      lastEquity,
      maxDrawdown,
      meanDeviation,
      p95Divergence,
      maxDivergence,
      correlation,
      drawdownDivergence,
    }
  }, [data])

  const trackingSeries = useMemo(() => {
    return buildTrackingSeries(data?.equity_theoretical, data?.equity_realistic)
  }, [data])

  if (isLoading) {
    return (
      <section className="signal-compliance" aria-busy="true">
        <header>
          <h2>Seguimiento de Señales</h2>
        </header>
        <p>Cargando desempeño de señales...</p>
      </section>
    )
  }

  if (isError || !data || data.timeline.length === 0) {
    return (
      <section className="signal-compliance" aria-live="polite">
        <header>
          <h2>Seguimiento de Señales</h2>
        </header>
        <p>No hay suficiente histórico para evaluar cumplimiento.</p>
      </section>
    )
  }

  return (
    <section className="signal-compliance">
      <header>
        <h2>Seguimiento de Señales</h2>
        <div className="signal-compliance-metrics">
          <div>
            <span className="metric-label">Win rate</span>
            <span className="metric-value">{formatPercent(metrics.winRate)}</span>
          </div>
          <div>
            <span className="metric-label">Tracking error</span>
            <span className="metric-value">{formatPercent(metrics.trackingError)}</span>
          </div>
          <div>
            <span className="metric-label">Equity (β1)</span>
            <span className="metric-value">{metrics.lastEquity.toFixed(3)}x</span>
          </div>
          <div>
            <span className="metric-label">Drawdown máx.</span>
            <span className="metric-value">{formatPercent(metrics.maxDrawdown)}</span>
          </div>
          <div>
            <span className="metric-label">Desviación media</span>
            <span className="metric-value">{metrics.meanDeviation.toFixed(4)}</span>
          </div>
          <div>
            <span className="metric-label">P95 divergencia</span>
            <span className="metric-value">{metrics.p95Divergence.toFixed(4)}</span>
          </div>
          <div>
            <span className="metric-label">Correlación</span>
            <span className="metric-value">{(metrics.correlation * 100).toFixed(1)}%</span>
          </div>
          <div>
            <span className="metric-label">Trades evaluados</span>
            <span className="metric-value">{metrics.trades}</span>
          </div>
        </div>
      </header>

      {trackingSeries.length > 0 && (
        <div className="signal-compliance-chart">
          <h3>Curvas de Equity: Teórico vs Realista</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={trackingSeries} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="fillError" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0.0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.1)" />
              <XAxis dataKey="index" stroke="rgba(255, 255, 255, 0.6)" />
              <YAxis stroke="rgba(255, 255, 255, 0.6)" />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'rgba(16, 23, 39, 0.95)',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  borderRadius: '8px',
                  color: '#fff',
                }}
                formatter={(value: number, name: string) => {
                  if (name === 'theoretical') return [`${value.toFixed(4)}x`, 'Teórico']
                  if (name === 'realistic') return [`${value.toFixed(4)}x`, 'Realista']
                  if (name === 'trackingError') return [`${value.toFixed(4)}`, 'Tracking Error']
                  return [value, name]
                }}
              />
              <Legend />
              <ReferenceLine y={1} stroke="rgba(255, 255, 255, 0.3)" strokeDasharray="2 2" />
              <Area
                type="monotone"
                dataKey="realistic"
                stroke="none"
                fill="url(#fillError)"
                fillOpacity={0.3}
              />
              <Line
                type="monotone"
                dataKey="theoretical"
                stroke="#10b981"
                strokeWidth={2}
                dot={false}
                name="Teórico (Sin Fricciones)"
                legendType="line"
              />
              <Line
                type="monotone"
                dataKey="realistic"
                stroke="#2563eb"
                strokeWidth={2}
                dot={false}
                name="Realista (Con Fricciones)"
                legendType="line"
              />
            </LineChart>
          </ResponsiveContainer>
          <div className="tracking-error-summary">
            <div className="summary-item">
              <span className="summary-label">Max Divergencia:</span>
              <span className="summary-value">{metrics.maxDivergence.toFixed(4)}</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Drawdown Divergencia:</span>
              <span className="summary-value">{formatPercent(metrics.drawdownDivergence)}</span>
            </div>
          </div>
        </div>
      )}

      <div className="signal-compliance-table-wrapper">
        <table className="signal-compliance-table">
          <caption>Señales emitidas vs resultado real</caption>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Señal</th>
              <th>Nivel alcanzado</th>
              <th>Retorno</th>
              <th>Desviación</th>
              <th>Tracking error</th>
              <th>Entrada / Salida</th>
              <th>Storytelling</th>
            </tr>
          </thead>
          <tbody>
            {data.timeline.map((row) => {
              const deviationPct = row.deviation_pct || 0
              const hasHighDeviation = deviationPct > DEVIATION_THRESHOLD
              
              return (
                <tr key={`${row.date}-${row.signal}`} className={hasHighDeviation ? 'high-deviation' : ''}>
                  <td>
                    <span className="date-cell">{row.date}</span>
                    <span className="holding">Hold {row.holding_days}d</span>
                  </td>
                  <td>
                    <span className={`signal-badge signal-${row.signal.toLowerCase()}`}>{row.signal}</span>
                  </td>
                  <td>
                    <strong>{row.level_hit}</strong>
                    <div className="price-cluster">
                      TP {formatPrice(row.take_profit)} / SL {formatPrice(row.stop_loss)}
                    </div>
                  </td>
                  <td className={row.return_pct >= 0 ? 'positive' : 'negative'}>
                    {formatPercent(row.return_pct)}
                    {row.return_pct_realistic !== undefined && row.return_pct_realistic !== row.return_pct && (
                      <div className="realistic-return">
                        Realista: {formatPercent(row.return_pct_realistic)}
                      </div>
                    )}
                  </td>
                  <td>
                    {deviationPct > 0 && (
                      <span className={`deviation-badge ${hasHighDeviation ? 'high' : 'normal'}`}>
                        {formatPercent(deviationPct)}
                      </span>
                    )}
                    {row.entry_slippage_pct !== undefined && row.exit_slippage_pct !== undefined && (
                      <div className="slippage-info">
                        Entry: {formatPercent(row.entry_slippage_pct)} / Exit: {formatPercent(row.exit_slippage_pct)}
                      </div>
                    )}
                  </td>
                  <td>{formatPercent(row.tracking_error)}</td>
                  <td>
                    <div className="price-cluster">
                      {formatPrice(row.entry_price)} → {formatPrice(row.exit_price)}
                      {row.entry_price_realistic !== undefined && row.exit_price_realistic !== undefined && (
                        <div className="realistic-prices">
                          Realista: {formatPrice(row.entry_price_realistic)} → {formatPrice(row.exit_price_realistic)}
                        </div>
                      )}
                    </div>
                    <span className="hit-date">{row.hit_date ? `Cierre: ${row.hit_date}` : 'Último close'}</span>
                  </td>
                  <td>
                    <ul className="narrative-list">
                      {(row.signal_breakdown?.narrative ?? []).map((line: string) => (
                        <li key={line}>{line}</li>
                      ))}
                    </ul>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default SignalCompliance
