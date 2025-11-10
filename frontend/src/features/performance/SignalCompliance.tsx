import { useMemo } from 'react'
import { useSignalPerformance } from '../../api/hooks'
import './SignalCompliance.css'

const formatPercent = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
const formatPrice = (value: number) => value.toFixed(2)

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
      }
    }
    const lastEquity = data.equity_curve.length > 0 ? data.equity_curve[data.equity_curve.length - 1] : 1
    const maxDrawdown =
      data.drawdown_curve.length > 0
        ? Math.min(...data.drawdown_curve)
        : 0

    return {
      winRate: data.win_rate,
      trackingError: data.average_tracking_error,
      trades: data.trades_evaluated,
      lastEquity,
      maxDrawdown,
    }
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
            <span className="metric-label">Trades evaluados</span>
            <span className="metric-value">{metrics.trades}</span>
          </div>
        </div>
      </header>

      <div className="signal-compliance-table-wrapper">
        <table className="signal-compliance-table">
          <caption>Señales emitidas vs resultado real</caption>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Señal</th>
              <th>Nivel alcanzado</th>
              <th>Retorno</th>
              <th>Tracking error</th>
              <th>Entrada / Salida</th>
              <th>Storytelling</th>
            </tr>
          </thead>
          <tbody>
            {data.timeline.map((row) => (
              <tr key={`${row.date}-${row.signal}`}>
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
                <td className={row.return_pct >= 0 ? 'positive' : 'negative'}>{formatPercent(row.return_pct)}</td>
                <td>{formatPercent(row.tracking_error)}</td>
                <td>
                  <div className="price-cluster">
                    {formatPrice(row.entry_price)} → {formatPrice(row.exit_price)}
                  </div>
                  <span className="hit-date">{row.hit_date ? `Cierre: ${row.hit_date}` : 'Último close'}</span>
                </td>
                <td>
                  <ul className="narrative-list">
                    {(row.signal_breakdown?.narrative ?? []).map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default SignalCompliance


