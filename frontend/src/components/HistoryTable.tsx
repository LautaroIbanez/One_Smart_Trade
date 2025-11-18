import { useMemo, useState } from 'react'
import { Line, LineChart, ResponsiveContainer, Tooltip } from 'recharts'
import { API_BASE_URL, RecommendationHistoryParams, useRecommendationHistory } from '../api/hooks'
import './HistoryTable.css'

const DEFAULT_LIMIT = 25
const SIGNAL_OPTIONS = [
  { label: 'Todas', value: '' },
  { label: 'Buy', value: 'BUY' },
  { label: 'Sell', value: 'SELL' },
  { label: 'Hold', value: 'HOLD' },
]
const RESULT_OPTIONS = [
  { label: 'Todos', value: '' },
  { label: 'Take Profit', value: 'TP' },
  { label: 'Stop Loss', value: 'SL' },
  { label: 'Manual', value: 'EXIT' },
]
const STATUS_OPTIONS = [
  { label: 'Todos', value: '' },
  { label: 'Abierto', value: 'open' },
  { label: 'Cerrado', value: 'closed' },
]

function HistoryTable() {
  const [filters, setFilters] = useState<RecommendationHistoryParams>({ limit: DEFAULT_LIMIT })
  const [cursor, setCursor] = useState<string | null>(null)
  const [cursorStack, setCursorStack] = useState<string[]>([])

  const params = useMemo(() => ({ ...filters, cursor }), [filters, cursor])
  const { data, isLoading, isFetching, error } = useRecommendationHistory(params)

  const items = data?.items ?? []
  const sparklineSeries = data?.insights?.sparkline_series ?? {}
  const stats = data?.insights?.stats

  const updateFilters = (next: Partial<RecommendationHistoryParams>) => {
    setFilters((prev) => ({ ...prev, ...next }))
    setCursor(null)
    setCursorStack([])
  }

  const handlePrevPage = () => {
    setCursorStack((prev) => {
      if (!prev.length) return prev
      const newStack = [...prev]
      const previousCursor = newStack.pop() || null
      setCursor(previousCursor)
      return newStack
    })
  }

  const handleNextPage = () => {
    if (!data?.next_cursor) return
    setCursorStack((prev) => [...prev, cursor || ''])
    setCursor(data.next_cursor)
  }

  const handleDownload = () => {
    if (!data?.download_url) return
    window.open(`${API_BASE_URL}${data.download_url}`, '_blank', 'noopener')
  }

  const handleReset = () => {
    setFilters({ limit: DEFAULT_LIMIT })
    setCursor(null)
    setCursorStack([])
  }

  const renderStatusChip = (item: any) => {
    const status = (item.execution_status || '').toLowerCase()
    return <span className={`status-chip status-${status}`}>{item.execution_status || item.status}</span>
  }

  return (
    <div className="history-table-container">
      <div className="history-header">
        <div>
          <h2>Historial de Ejecución</h2>
          <p>Audita la convergencia entre teoría y ejecución realista.</p>
        </div>
        <div className="history-header-actions">
          <button className="ghost-button" onClick={handleDownload} disabled={!data?.download_url || isFetching}>
            Descargar CSV
          </button>
          <button className="ghost-button" onClick={handleReset} disabled={isFetching}>
            Restablecer filtros
          </button>
        </div>
      </div>

      <div className="history-filters">
        <label>
          Inicio
          <input
            type="date"
            value={filters.start_date ?? ''}
            onChange={(e) => updateFilters({ start_date: e.target.value || null })}
          />
        </label>
        <label>
          Fin
          <input
            type="date"
            value={filters.end_date ?? ''}
            onChange={(e) => updateFilters({ end_date: e.target.value || null })}
          />
        </label>
        <label>
          Señal
          <select
            value={filters.signal ?? ''}
            onChange={(e) => updateFilters({ signal: (e.target.value as RecommendationHistoryParams['signal']) || '' })}
          >
            {SIGNAL_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Resultado
          <select value={filters.result ?? ''} onChange={(e) => updateFilters({ result: e.target.value || null })}>
            {RESULT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Estado
          <select value={filters.status ?? ''} onChange={(e) => updateFilters({ status: e.target.value || null })}>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Tracking ≥ (%)
          <input
            type="number"
            min={0}
            step={0.1}
            value={filters.tracking_error_min ?? ''}
            onChange={(e) => updateFilters({ tracking_error_min: e.target.value ? parseFloat(e.target.value) : null })}
            placeholder="0.0"
          />
        </label>
        <label>
          Tracking ≤ (%)
          <input
            type="number"
            min={0}
            step={0.1}
            value={filters.tracking_error_max ?? ''}
            onChange={(e) => updateFilters({ tracking_error_max: e.target.value ? parseFloat(e.target.value) : null })}
            placeholder="5.0"
          />
        </label>
        <label>
          Límite
          <select
            value={filters.limit ?? DEFAULT_LIMIT}
            onChange={(e) => updateFilters({ limit: Number(e.target.value) })}
          >
            {[10, 25, 50, 100].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
      </div>

      {isLoading ? (
        <div className="loading" role="status" aria-live="polite">
          Cargando historial...
        </div>
      ) : error ? (
        <div className="error" role="alert">
          Error al cargar historial
        </div>
      ) : items.length === 0 ? (
        <div className="empty">No hay historial disponible</div>
      ) : (
        <>
        <div className="table-wrapper">
          <table className="history-table" aria-label="Historial de recomendaciones">
            <thead>
              <tr>
                <th scope="col">Fecha</th>
                <th scope="col">Señal</th>
                  <th scope="col">Entrada → Salida</th>
                  <th scope="col">Retorno</th>
                  <th scope="col">Tracking Error</th>
                  <th scope="col">Ejecución</th>
                  <th scope="col">Snapshot</th>
              </tr>
            </thead>
            <tbody>
                {items.map((item: any) => (
                  <tr key={item.id}>
                    <td>
                      <div className="cell-date">
                        <span>{new Date(item.timestamp).toLocaleDateString('es-ES')}</span>
                        <span className="cell-time">{new Date(item.timestamp).toLocaleTimeString('es-ES')}</span>
                      </div>
                    </td>
                    <td>
                      <span className={`signal-badge signal-${item.signal?.toLowerCase()}`} aria-label={`Señal: ${item.signal}`}>
                        {item.signal}
                    </span>
                  </td>
                    <td>
                      <div className="price-stack">
                        <span>Entrada: ${item.entry_price?.toLocaleString()}</span>
                        <span>Salida: {item.exit_price ? `$${item.exit_price.toLocaleString()}` : '—'}</span>
                      </div>
                    </td>
                    <td>
                      <div className="return-stack">
                        <span className={item.return_pct >= 0 ? 'positive' : 'negative'}>
                          Real: {item.return_pct?.toFixed(2) ?? '0.00'}%
                        </span>
                        <span className="muted">Teórica: {item.theoretical_return_pct?.toFixed(2) ?? '0.00'}%</span>
                      </div>
                    </td>
                    <td>
                      <div className={`tracking-chip ${item.divergence_flag ? 'danger' : 'ok'}`}>
                        {item.tracking_error_pct !== null && item.tracking_error_pct !== undefined
                          ? `${item.tracking_error_pct.toFixed(2)}%`
                          : '—'}
                      </div>
                    </td>
                    <td>{renderStatusChip(item)}</td>
                    <td>
                      {item.snapshot_url ? (
                        <a className="link-button" href={item.snapshot_url} target="_blank" rel="noreferrer">
                          Ver snapshot
                        </a>
                      ) : (
                        <span className="muted">No disponible</span>
                      )}
                    </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

          <div className="history-footer">
            <div>
              {stats && (
                <p>
                  Registros: {stats.count?.toFixed(0)} · Tracking promedio: {stats.avg_tracking_error_pct?.toFixed(2)}% ·
                  Divergencia: {stats.divergence_rate_pct?.toFixed(1)}%
                </p>
              )}
            </div>
            <div className="pagination-controls">
              <button onClick={handlePrevPage} disabled={!cursorStack.length || isFetching}>
                ← Anterior
              </button>
              <button onClick={handleNextPage} disabled={!data?.has_more || !data?.next_cursor || isFetching}>
                Siguiente →
              </button>
            </div>
          </div>
        </>
      )}

      <div className="sparklines-grid">
        {Object.entries(sparklineSeries).map(([signal, series]) => (
          <SparklineCard key={signal} signal={signal} data={series as any[]} />
        ))}
      </div>
    </div>
  )
}

interface SparklineProps {
  signal: string
  data: Array<{ timestamp: string; theoretical: number; realistic: number }>
}

const SparklineCard = ({ signal, data }: SparklineProps) => {
  if (!data || data.length === 0) {
    return (
      <div className="sparkline-card">
        <h4>{signal}</h4>
        <p className="muted">Sin datos suficientes</p>
      </div>
    )
  }

  return (
    <div className="sparkline-card">
      <h4>{signal}</h4>
      <ResponsiveContainer width="100%" height={80}>
        <LineChart data={data}>
          <Tooltip
            contentStyle={{ background: 'rgba(15,23,42,0.9)', border: 'none', borderRadius: '0.5rem', color: '#fff' }}
            formatter={(value: number, name: string) => {
              const label = name === 'theoretical' ? 'Teórico' : 'Realista'
              return [`${value.toFixed(2)}`, label]
            }}
            labelFormatter={(label) => new Date(label).toLocaleDateString('es-ES')}
          />
          <Line type="monotone" dataKey="theoretical" stroke="#38bdf8" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="realistic" stroke="#f97316" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export default HistoryTable

