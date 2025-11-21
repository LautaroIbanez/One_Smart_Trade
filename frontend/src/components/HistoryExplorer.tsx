import { useState, useMemo, useCallback } from 'react'
import { format, subDays, startOfDay, endOfDay, isWithinInterval, parseISO } from 'date-fns'
import { useRecommendationHistory, isTimeoutError, getErrorMessage } from '../api/hooks'
import { ErrorState } from './shared/ErrorState'
import { LoadingState } from './shared/LoadingState'
import { DegradedDataBanner } from './shared/DegradedDataBanner'
import { WeeklyHeatmap } from './charts/WeeklyHeatmap'
import { ReturnsHistogram } from './charts/ReturnsHistogram'
import HistoryRow from './HistoryRow'
import './HistoryExplorer.css'
import './HistoryRow.css'

export interface HistoryFilters {
  dateRange: { from: Date | null; to: Date | null }
  signal: string[]
  outcome: string[]
  minConfidence: number
}

interface HistoryExplorerProps {
  defaultPageSize?: number
  filters?: Partial<HistoryFilters>
  onFilterChange?: (filters: HistoryFilters) => void
}

const QUICK_FILTERS = {
  last7Days: () => ({ from: subDays(new Date(), 7), to: new Date() }),
  last30Days: () => ({ from: subDays(new Date(), 30), to: new Date() }),
  last90Days: () => ({ from: subDays(new Date(), 90), to: new Date() }),
}

function HistoryExplorer({
  defaultPageSize = 25,
  filters: initialFilters,
  onFilterChange,
}: HistoryExplorerProps) {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(defaultPageSize)
  const [expandedRow, setExpandedRow] = useState<string | null>(null)
  const [filters, setFilters] = useState<HistoryFilters>({
    dateRange: { from: null, to: null },
    signal: [],
    outcome: [],
    minConfidence: 0,
    ...initialFilters,
  })

  const { data, isLoading, error, refetch } = useRecommendationHistory({ limit: 1000 })

  const recommendations = data?.items || []

  const filteredRecommendations = useMemo(() => {
    return recommendations.filter((rec: any) => {
      if (filters.dateRange.from || filters.dateRange.to) {
        const recDate = parseISO(rec.timestamp)
        const interval = {
          start: filters.dateRange.from ? startOfDay(filters.dateRange.from) : new Date(0),
          end: filters.dateRange.to ? endOfDay(filters.dateRange.to) : new Date(),
        }
        if (!isWithinInterval(recDate, interval)) return false
      }

      if (filters.signal.length > 0 && !filters.signal.includes(rec.signal)) {
        return false
      }

      if (filters.outcome.length > 0) {
        const outcome = rec.exit_reason || rec.status || 'open'
        if (!filters.outcome.includes(outcome)) return false
      }

      if (filters.minConfidence > 0 && (rec.confidence || 0) < filters.minConfidence) {
        return false
      }

      return true
    })
  }, [recommendations, filters])

  const paginatedRecommendations = useMemo(() => {
    const start = (page - 1) * pageSize
    const end = start + pageSize
    return filteredRecommendations.slice(start, end)
  }, [filteredRecommendations, page, pageSize])

  const totalPages = Math.ceil(filteredRecommendations.length / pageSize)

  const handleFilterChange = useCallback(
    (newFilters: Partial<HistoryFilters>) => {
      const updated = { ...filters, ...newFilters }
      setFilters(updated)
      setPage(1)
      onFilterChange?.(updated)
    },
    [filters, onFilterChange]
  )

  const handleQuickFilter = useCallback(
    (filterKey: keyof typeof QUICK_FILTERS) => {
      const dateRange = QUICK_FILTERS[filterKey]()
      handleFilterChange({ dateRange })
    },
    [handleFilterChange]
  )

  const handleSignalFilter = useCallback(
    (signal: string) => {
      const newSignals = filters.signal.includes(signal)
        ? filters.signal.filter((s) => s !== signal)
        : [...filters.signal, signal]
      handleFilterChange({ signal: newSignals })
    },
    [filters.signal, handleFilterChange]
  )

  const handleOutcomeFilter = useCallback(
    (outcome: string) => {
      const newOutcomes = filters.outcome.includes(outcome)
        ? filters.outcome.filter((o) => o !== outcome)
        : [...filters.outcome, outcome]
      handleFilterChange({ outcome: newOutcomes })
    },
    [filters.outcome, handleFilterChange]
  )

  const chartData = useMemo(() => {
    return filteredRecommendations
      .filter((rec: any) => rec.timestamp)
      .map((rec: any) => ({
        date: parseISO(rec.timestamp),
        return: rec.return_pct || rec.pnl_pct || 0,
        outcome: rec.exit_reason || rec.status || 'open',
        signal: rec.signal || 'UNKNOWN',
      }))
  }, [filteredRecommendations])

  const availableSignals = useMemo(() => {
    return Array.from(new Set(recommendations.map((rec: any) => rec.signal))).filter(Boolean)
  }, [recommendations])

  const availableOutcomes = useMemo(() => {
    return Array.from(
      new Set(recommendations.map((rec: any) => rec.exit_reason || rec.status || 'open'))
    ).filter(Boolean)
  }, [recommendations])

  if (isLoading && !data) {
    return (
      <div className="history-explorer">
        <div className="history-explorer-header">
          <h2>Explorador de Historial</h2>
        </div>
        <LoadingState message="Cargando historial de recomendaciones..." />
      </div>
    )
  }

  if (error && !data) {
    return (
      <div className="history-explorer">
        <div className="history-explorer-header">
          <h2>Explorador de Historial</h2>
        </div>
        <ErrorState 
          error={error} 
          title="Error al cargar historial"
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  const showDegradedBanner = error && data && (data as any).metadata?.served_from_cache

  return (
    <div className="history-explorer">
      <div className="history-explorer-header">
        <h2>Explorador de Historial</h2>
        <div className="results-count">
          {filteredRecommendations.length} de {recommendations.length} registros
        </div>
      </div>
      {showDegradedBanner && (
        <DegradedDataBanner 
          message="Mostrando historial desde caché."
          source={(data as any).metadata?.source}
          cachedAt={(data as any).metadata?.generated_at}
        />
      )}

      <div className="history-explorer-filters">
        <div className="filter-section">
          <label className="filter-label">Filtros Rápidos</label>
          <div className="quick-filter-chips">
            <button
              type="button"
              className={`chip ${filters.dateRange.from?.getTime() === QUICK_FILTERS.last7Days().from.getTime() ? 'active' : ''}`}
              onClick={() => handleQuickFilter('last7Days')}
            >
              Últimos 7 días
            </button>
            <button
              type="button"
              className={`chip ${filters.dateRange.from?.getTime() === QUICK_FILTERS.last30Days().from.getTime() ? 'active' : ''}`}
              onClick={() => handleQuickFilter('last30Days')}
            >
              Últimos 30 días
            </button>
            <button
              type="button"
              className={`chip ${filters.dateRange.from?.getTime() === QUICK_FILTERS.last90Days().from.getTime() ? 'active' : ''}`}
              onClick={() => handleQuickFilter('last90Days')}
            >
              Últimos 90 días
            </button>
          </div>
        </div>

        <div className="filter-section">
          <label className="filter-label">Rango de Fechas</label>
          <div className="date-range-inputs">
            <input
              type="date"
              value={filters.dateRange.from ? format(filters.dateRange.from, 'yyyy-MM-dd') : ''}
              onChange={(e) =>
                handleFilterChange({
                  dateRange: { ...filters.dateRange, from: e.target.value ? new Date(e.target.value) : null },
                })
              }
              className="date-input"
            />
            <span className="date-separator">-</span>
            <input
              type="date"
              value={filters.dateRange.to ? format(filters.dateRange.to, 'yyyy-MM-dd') : ''}
              onChange={(e) =>
                handleFilterChange({
                  dateRange: { ...filters.dateRange, to: e.target.value ? new Date(e.target.value) : null },
                })
              }
              className="date-input"
            />
          </div>
        </div>

        <div className="filter-section">
          <label className="filter-label">Tipo de Señal</label>
          <div className="signal-filter-chips">
            {availableSignals.map((signal: string) => (
              <button
                key={signal}
                type="button"
                className={`chip signal-chip signal-${signal.toLowerCase()} ${filters.signal.includes(signal) ? 'active' : ''}`}
                onClick={() => handleSignalFilter(signal)}
              >
                {signal}
              </button>
            ))}
          </div>
        </div>

        <div className="filter-section">
          <label className="filter-label">Estado (TP/SL/Exit Manual)</label>
          <div className="outcome-filter-chips">
            {availableOutcomes.map((outcome: string) => (
              <button
                key={outcome}
                type="button"
                className={`chip outcome-chip ${filters.outcome.includes(outcome) ? 'active' : ''}`}
                onClick={() => handleOutcomeFilter(outcome)}
              >
                {outcome}
              </button>
            ))}
          </div>
        </div>

        <div className="filter-section">
          <label className="filter-label">
            Confianza Mínima: {filters.minConfidence}%
          </label>
          <input
            type="range"
            min="0"
            max="100"
            value={filters.minConfidence}
            onChange={(e) => handleFilterChange({ minConfidence: Number(e.target.value) })}
            className="confidence-slider"
          />
        </div>

        {(filters.dateRange.from || filters.dateRange.to || filters.signal.length > 0 || filters.outcome.length > 0 || filters.minConfidence > 0) && (
          <button
            type="button"
            className="clear-filters-button"
            onClick={() => {
              const cleared = {
                dateRange: { from: null, to: null },
                signal: [],
                outcome: [],
                minConfidence: 0,
              }
              setFilters(cleared)
              onFilterChange?.(cleared)
              setPage(1)
            }}
          >
            Limpiar Filtros
          </button>
        )}
      </div>

      <div className="history-explorer-charts">
        <div className="chart-container">
          <h3>Heatmap Semanal de Aciertos</h3>
          <WeeklyHeatmap data={chartData} />
        </div>
        <div className="chart-container">
          <h3>Histograma de Retornos</h3>
          <ReturnsHistogram data={chartData} />
        </div>
      </div>

      <div className="history-explorer-table">
        <div className="table-header">
          <div className="table-controls">
            <label>
              Por página:{' '}
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value))
                  setPage(1)
                }}
                className="page-size-select"
              >
                <option value={10}>10</option>
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </label>
          </div>
        </div>

        <div className="table-container">
          <table className="history-table">
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Señal</th>
                <th>Precio</th>
                <th>Confianza</th>
                <th>Estado</th>
                <th>Retorno</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {paginatedRecommendations.length === 0 ? (
                <tr>
                  <td colSpan={7} className="empty-message">
                    No hay recomendaciones que coincidan con los filtros seleccionados
                  </td>
                </tr>
              ) : (
                paginatedRecommendations.map((rec: any, index: number) => (
                  <HistoryRow
                    key={rec.id || rec.timestamp || index}
                    recommendation={rec}
                    isExpanded={expandedRow === (rec.id || rec.timestamp || String(index))}
                    onExpand={() =>
                      setExpandedRow(
                        expandedRow === (rec.id || rec.timestamp || String(index))
                          ? null
                          : rec.id || rec.timestamp || String(index)
                      )
                    }
                  />
                ))
              )}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="pagination">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="pagination-button"
            >
              Anterior
            </button>
            <span className="pagination-info">
              Página {page} de {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="pagination-button"
            >
              Siguiente
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default HistoryExplorer

