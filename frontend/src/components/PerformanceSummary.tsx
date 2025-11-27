import { useMemo, useEffect, useState } from 'react'
import { usePerformanceSummary, useCalculatePerformanceSummary, isTimeoutError, isBackendDown, isEmptyDatabase, getErrorMessage } from '../api/hooks'
import './PerformanceSummary.css'

function PerformanceSummary() {
  const { data, isLoading, error, refetch } = usePerformanceSummary()
  const calculatePerformance = useCalculatePerformanceSummary()
  const [isCalculating, setIsCalculating] = useState(false)

  // Check if status is degraded
  const isDegradedStatus = data?.status === 'degraded'
  const isDemoMetrics = data?.has_realistic_data === false && isDegradedStatus

  // Extract data from main payload or fallback_summary
  // Always attempt to extract partial/fallback data
  const effectiveData = useMemo(() => {
    // Provide safe defaults if data is null/undefined
    if (!data) {
      return {
        status: 'degraded' as const,
        metrics: {
          total_trades: 0,
          winning_trades: 0,
          losing_trades: 0,
          win_rate: 0,
          profit_factor: 1.0,
          sharpe_ratio: 0.0,
          calmar_ratio: 0.0,
          max_drawdown: 0.0,
          cagr: 0.0,
          expectancy_r: 0.0,
          avg_rr: 1.0,
        },
        equity_curve: [],
        equity_theoretical: [],
        equity_realistic: [],
        degraded_mode: true,
        dev_fallback: true,
        message: 'No hay datos disponibles. Las métricas se están calculando.',
      }
    }
    
    const dataAny = data as any
    
    // Check if this is a dev fallback response
    const isDevFallback = dataAny.dev_fallback === true || dataAny.degraded_mode === true
    
    // Check for fallback_summary in various places
    const fallbackSummary = dataAny.fallback_summary || dataAny.summary_fallback || null
    
    // If status is error but we have fallback_summary, use it
    if (data.status === 'error' && fallbackSummary) {
      return {
        ...data,
        metrics: data.metrics || fallbackSummary.metrics || {},
        period: data.period || fallbackSummary.period || null,
        report_path: data.report_path || fallbackSummary.report_path || null,
        _isDegraded: true,
        _isDevFallback: isDevFallback,
        _degradedMessage: data.message || 'Datos en modo degradado',
      }
    }
    
    // If status is error but we have partial metrics, use them
    if (data.status === 'error' && data.metrics && Object.keys(data.metrics).length > 0) {
      return {
        ...data,
        _isDegraded: true,
        _isDevFallback: isDevFallback,
        _degradedMessage: data.message || 'Mostrando métricas parciales',
      }
    }
    
    // If status is degraded/success and we have metrics, ensure arrays are present
    if ((data.status === 'degraded' || data.status === 'success') && data.metrics) {
      return {
        ...data,
        _isDegraded: data.status === 'degraded' || isDevFallback,
        _isDevFallback: isDevFallback,
        equity_curve: dataAny.equity_curve || [],
        equity_theoretical: dataAny.equity_theoretical || [],
        equity_realistic: dataAny.equity_realistic || [],
      }
    }
    
    // If we have any metrics at all, show them
    if (data.metrics && Object.keys(data.metrics).length > 0) {
      return {
        ...data,
        _isDegraded: isDevFallback || data.status === 'degraded',
        _isDevFallback: isDevFallback,
      }
    }
    
    // Return data anyway to show placeholder message
    return {
      ...data,
      _isDegraded: true,
      _isDevFallback: isDevFallback,
    }
  }, [data])

  const isDegraded = (effectiveData as any)?._isDegraded === true || isDegradedStatus
  const isDevFallback = (effectiveData as any)?._isDevFallback === true || (data as any)?.dev_fallback === true
  const degradedMessage = isDemoMetrics 
    ? (data?.message || 'Mostrando métricas demo. Los datos reales se están calculando en segundo plano.')
    : isDevFallback
    ? (data?.message || 'Modo desarrollo: Mostrando métricas de respaldo generadas automáticamente.')
    : ((effectiveData as any)?._degradedMessage || data?.message || 'Modo degradado')

  // Note: Auto-refresh is now handled by React Query's refetchInterval
  // in usePerformanceSummary hook, which uses centralized polling logic.
  // No manual setInterval needed - React Query will handle polling based on status.

  const handleCalculate = async () => {
    setIsCalculating(true)
    try {
      await calculatePerformance.mutateAsync(false)
      // After successful calculation, refetch to get the new metrics
      await refetch()
    } catch (err) {
      console.error('Error calculating performance:', err)
    } finally {
      setIsCalculating(false)
    }
  }

  if (isLoading || isCalculating) {
    return (
      <div className="performance-summary" role="status" aria-live="polite">
        <h2>Resumen de Performance</h2>
        <div className="loading">Cargando métricas...</div>
      </div>
    )
  }

  if (error && !data) {
    const isTimeout = isTimeoutError(error)
    const errorMessage = getErrorMessage(error)
    return (
      <div className="performance-summary error" role="alert" aria-live="assertive">
        <h2>Resumen de Performance</h2>
        <div className="error-message">
          {isTimeout ? (
            <div className="timeout-error">
              <p><strong>⏱️ Tiempo de espera excedido (25s)</strong></p>
              <p>El backend puede estar ejecutando el pipeline inicial o ingiriendo datos.</p>
              <div style={{ marginTop: '1rem', fontSize: '0.875rem' }}>
                <p><strong>Pasos para solucionar:</strong></p>
                <ol style={{ marginTop: '0.5rem', paddingLeft: '1.5rem' }}>
                  <li>Espera a que termine el pipeline (puede tardar varios minutos)</li>
                  <li>Verifica en los logs del backend que el pipeline haya finalizado</li>
                  <li>Después de que termine, recarga esta página (F5 o Ctrl+R)</li>
                </ol>
              </div>
            </div>
          ) : (
            <div className="error-details">
              <p><strong>❌ Error al cargar métricas</strong></p>
              <p>{errorMessage}</p>
            </div>
          )}
        </div>
      </div>
    )
  }

  // NEVER return null - always show the component with a message
  // Show component even if no effectiveData - we'll show a placeholder
  const metrics = effectiveData?.metrics || (data as any)?.metrics || {}
  const hasMetrics = Object.keys(metrics).length > 0

  return (
    <div className="performance-summary">
      <h2>Resumen de Performance (Backtesting)</h2>
      {isDegraded && (
        <div className="degraded-mode-banner" role="status" aria-live="polite" style={{
          padding: '1rem',
          backgroundColor: isDevFallback ? 'rgba(147, 51, 234, 0.1)' : 'rgba(245, 158, 11, 0.1)',
          border: `1px solid ${isDevFallback ? 'rgba(147, 51, 234, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
          borderRadius: '0.5rem',
          marginBottom: '1rem',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
            <div style={{ flex: 1 }}>
              <p style={{ margin: 0, fontWeight: 600, color: isDevFallback ? '#9333ea' : '#f59e0b' }}>
                {isDevFallback ? '🔧 Modo Desarrollo' : isDemoMetrics ? '⚠️ Métricas Demo' : '⚠️ Modo Degradado'}
              </p>
              <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.875rem', color: 'rgba(255, 255, 255, 0.8)' }}>
                {degradedMessage}
              </p>
              {isDevFallback && (
                <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.75rem', fontStyle: 'italic', color: 'rgba(255, 255, 255, 0.6)' }}>
                  Las métricas mostradas son valores de respaldo generados automáticamente en modo desarrollo. No reflejan resultados reales de backtesting.
                </p>
              )}
              {isDemoMetrics && !isDevFallback && (
                <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.75rem', fontStyle: 'italic', color: 'rgba(255, 255, 255, 0.6)' }}>
                  Las métricas reales se están calculando en segundo plano. Esta página se actualizará automáticamente cuando estén listas.
                </p>
              )}
            </div>
            <button
              onClick={handleCalculate}
              type="button"
              disabled={isCalculating}
              style={{
                padding: '0.5rem 1rem',
                backgroundColor: '#10b981',
                color: 'white',
                border: 'none',
                borderRadius: '0.375rem',
                cursor: isCalculating ? 'not-allowed' : 'pointer',
                fontWeight: 500,
                fontSize: '0.875rem',
                opacity: isCalculating ? 0.6 : 1,
              }}
            >
              {isCalculating ? '⏳ Calculando...' : '✨ Calcular Ahora'}
            </button>
          </div>
        </div>
      )}
      {hasMetrics ? (
        <>
          <div className="metrics-grid">
            <div className="metric-item">
              <span className="metric-label">CAGR</span>
              <span className="metric-value">{metrics.cagr?.toFixed(2)}%</span>
            </div>
            <div className="metric-item">
              <span className="metric-label">Sharpe</span>
              <span className="metric-value">{metrics.sharpe?.toFixed(2)}</span>
            </div>
            <div className="metric-item">
              <span className="metric-label">Max DD</span>
              <span className="metric-value">{metrics.max_drawdown?.toFixed(2)}%</span>
            </div>
            <div className="metric-item">
              <span className="metric-label">Win Rate</span>
              <span className="metric-value">{metrics.win_rate?.toFixed(1)}%</span>
            </div>
            <div className="metric-item">
              <span className="metric-label">Profit Factor</span>
              <span className="metric-value">{metrics.profit_factor?.toFixed(2)}</span>
            </div>
            <div className="metric-item">
              <span className="metric-label">Total Trades</span>
              <span className="metric-value">{metrics.total_trades || 0}</span>
            </div>
          </div>
          {effectiveData?.report_path ? (
            <div className="report-link">
              <a href={effectiveData.report_path} target="_blank" rel="noreferrer">
                Ver reporte completo
              </a>
            </div>
          ) : (
            <div className="no-metrics-placeholder">
              <p>⚠️ Métricas no disponibles en modo degradado</p>
              <p>Los datos frescos no están disponibles y no hay métricas almacenadas para mostrar.</p>
            </div>
          )}
        </>
      ) : (
        <div className="no-metrics-placeholder">
          <p>⚠️ <strong>Sin métricas disponibles aún</strong></p>
          {isDegraded ? (
            <p>Los datos frescos no están disponibles y no hay métricas almacenadas en caché para mostrar.</p>
          ) : data?.status === 'error' ? (
            <p>Error al generar métricas. Los datos pueden estar procesándose en segundo plano.</p>
          ) : (
            <p>Las métricas se están calculando. Por favor, espera unos momentos o intenta refrescar.</p>
          )}
        </div>
      )}
    </div>
  )
}

export default PerformanceSummary

