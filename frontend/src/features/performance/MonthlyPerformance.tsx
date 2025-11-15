import { useMemo, useState, useCallback } from 'react'
import { useMonthlyPerformance } from '../../api/hooks'
import axios from 'axios'
import './MonthlyPerformance.css'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const api = axios.create({ baseURL: API_BASE_URL, headers: { 'Content-Type': 'application/json' } })

const formatPercent = (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(2)}%`

interface MonthlyReturn {
  month: string
  year: number
  month_num: number
  return_pct: number
  trade_count: number
  wins: number
  losses: number
  win_rate: number
}

interface MonthlyPerformanceData {
  status: string
  monthly_returns: MonthlyReturn[]
  best_month: MonthlyReturn | null
  worst_month: MonthlyReturn | null
  current_streak: { type: string; count: number }
  current_drawdown: number
  peak_equity: number
  current_equity: number
  total_trades: number
}

export function MonthlyPerformance() {
  const [pollingEnabled, setPollingEnabled] = useState(true)
  const { data, isLoading, isError, refetch } = useMonthlyPerformance(pollingEnabled ? 30000 : false)

  const metrics = useMemo(() => {
    if (!data) {
      return {
        bestMonth: null,
        worstMonth: null,
        currentStreak: { type: 'none', count: 0 },
        currentDrawdown: 0,
        peakEquity: 0,
        currentEquity: 0,
      }
    }

    return {
      bestMonth: data.best_month,
      worstMonth: data.worst_month,
      currentStreak: data.current_streak,
      currentDrawdown: data.current_drawdown,
      peakEquity: data.peak_equity,
      currentEquity: data.current_equity,
    }
  }, [data])

  const handleExport = useCallback(async () => {
    try {
      const response = await api.get('/api/v1/performance/monthly/export', {
        params: { format: 'csv' },
        responseType: 'blob',
      })

      const contentDisposition = response.headers['content-disposition']
      const filename = contentDisposition
        ? contentDisposition.split('filename=')[1].replace(/"/g, '')
        : `monthly_report_${new Date().toISOString().split('T')[0]}.csv`

      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', filename)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Error exporting monthly report:', error)
      alert('Error al exportar el reporte mensual')
    }
  }, [])

  if (isLoading) {
    return (
      <section className="monthly-performance" aria-busy="true">
        <header>
          <h2>Rendimiento Mensual</h2>
        </header>
        <p>Cargando rendimiento mensual...</p>
      </section>
    )
  }

  if (isError || !data || data.status === 'no_data') {
    return (
      <section className="monthly-performance" aria-live="polite">
        <header>
          <h2>Rendimiento Mensual</h2>
        </header>
        <p>No hay suficiente histórico para mostrar rendimiento mensual.</p>
      </section>
    )
  }

  const monthlyReturns = data.monthly_returns || []

  return (
    <section className="monthly-performance">
      <header>
        <div className="monthly-header-row">
          <h2>Rendimiento Mensual</h2>
          <div className="monthly-actions">
            <label className="polling-toggle">
              <input
                type="checkbox"
                checked={pollingEnabled}
                onChange={(e) => setPollingEnabled(e.target.checked)}
              />
              <span>Actualización automática</span>
            </label>
            <button type="button" className="export-button" onClick={handleExport}>
              📥 Exportar Reporte
            </button>
            <button type="button" className="refresh-button" onClick={() => refetch()}>
              🔄 Actualizar
            </button>
          </div>
        </div>

        <div className="monthly-cards">
          <div className="streak-card">
            <div className="card-label">Racha Actual</div>
            <div className={`card-value streak-${metrics.currentStreak.type}`}>
              {metrics.currentStreak.type === 'win' && '🔥 '}
              {metrics.currentStreak.type === 'loss' && '⚠️ '}
              {metrics.currentStreak.type === 'none' && '— '}
              {metrics.currentStreak.count} {metrics.currentStreak.type === 'win' ? 'victorias' : metrics.currentStreak.type === 'loss' ? 'derrotas' : 'ninguna'}
            </div>
          </div>

          <div className="drawdown-card">
            <div className="card-label">Drawdown Vigente</div>
            <div className={`card-value drawdown-${metrics.currentDrawdown > 10 ? 'high' : metrics.currentDrawdown > 5 ? 'medium' : 'low'}`}>
              {formatPercent(metrics.currentDrawdown)}
            </div>
            <div className="card-detail">
              Peak: {metrics.peakEquity.toFixed(2)} | Actual: {metrics.currentEquity.toFixed(2)}
            </div>
          </div>

          {metrics.bestMonth && (
            <div className="best-month-card">
              <div className="card-label">Mejor Mes</div>
              <div className="card-value positive">
                {metrics.bestMonth.month} ({formatPercent(metrics.bestMonth.return_pct)})
              </div>
              <div className="card-detail">
                {metrics.bestMonth.trade_count} trades, {formatPercent(metrics.bestMonth.win_rate)} win rate
              </div>
            </div>
          )}

          {metrics.worstMonth && (
            <div className="worst-month-card">
              <div className="card-label">Peor Mes</div>
              <div className="card-value negative">
                {metrics.worstMonth.month} ({formatPercent(metrics.worstMonth.return_pct)})
              </div>
              <div className="card-detail">
                {metrics.worstMonth.trade_count} trades, {formatPercent(metrics.worstMonth.win_rate)} win rate
              </div>
            </div>
          )}
        </div>
      </header>

      <div className="monthly-table-wrapper">
        <table className="monthly-table">
          <caption>Retornos Mensuales</caption>
          <thead>
            <tr>
              <th>Mes</th>
              <th>Retorno</th>
              <th>Trades</th>
              <th>Victorias</th>
              <th>Derrotas</th>
              <th>Win Rate</th>
            </tr>
          </thead>
          <tbody>
            {monthlyReturns.map((month) => (
              <tr
                key={month.month}
                className={
                  month.month === metrics.bestMonth?.month
                    ? 'best-month-row'
                    : month.month === metrics.worstMonth?.month
                    ? 'worst-month-row'
                    : ''
                }
              >
                <td>
                  <span className="month-cell">{month.month}</span>
                </td>
                <td className={month.return_pct >= 0 ? 'positive' : 'negative'}>
                  {formatPercent(month.return_pct)}
                </td>
                <td>{month.trade_count}</td>
                <td className="wins">{month.wins}</td>
                <td className="losses">{month.losses}</td>
                <td>{formatPercent(month.win_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default MonthlyPerformance

