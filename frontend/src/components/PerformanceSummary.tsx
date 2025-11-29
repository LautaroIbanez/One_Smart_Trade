import { useMemo, useEffect, useState } from 'react'
import { usePerformanceSummary, useCalculatePerformanceSummary, useDataStatus, usePipelineStatus, isTimeoutError, isBackendDown, isEmptyDatabase, getErrorMessage } from '../api/hooks'
import './PerformanceSummary.css'

function PerformanceSummary() {
  const { data, isLoading, error, refetch } = usePerformanceSummary()
  const calculatePerformance = useCalculatePerformanceSummary()
  const [isCalculating, setIsCalculating] = useState(false)
  const [showWarningModal, setShowWarningModal] = useState(false)
  
  // Fetch data status to check latest_open_time
  const { data: dataStatus } = useDataStatus('1d', 'BTCUSDT', 'binance', true)
  
  // Fetch pipeline status to check if pipeline is running
  const { data: pipelineStatus } = usePipelineStatus(true)
  const isPipelineRunning = pipelineStatus?.status === 'processing' || pipelineStatus?.pipeline?.running === true

  // Check if status is degraded
  const isDegradedStatus = data?.status === 'degraded'
  const isDemoMetrics = data?.has_realistic_data === false && isDegradedStatus
  
  // Extract metrics_status and related fields from API response
  const metricsStatus = (data as any)?.metrics_status
  const devBypass = (data as any)?.dev_bypass
  const fallbackReason = (data as any)?.fallback_reason
  const degradedReason = (data as any)?.degraded_reason
  const cacheMiss = (data as any)?.cache_miss
  const noTradeDiagnostics = (data as any)?.no_trade_diagnostics
  const noTradeRootCause = (data as any)?.no_trade_root_cause || noTradeDiagnostics?.root_cause
  const tradeCount = (data as any)?.trade_count ?? data?.metrics?.total_trades
  
  // Determine if metrics should be de-emphasized
  const shouldDeemphasizeKPIs = metricsStatus && metricsStatus !== 'PASS'
  
  // Check if we should show warning modal based on backend freshness flags and metrics_status
  // Don't show if pipeline is running (data is being updated)
  useEffect(() => {
    if (!dataStatus || !data) return
    
    // Don't show warning if pipeline is actively running (data is being updated)
    if (isPipelineRunning) {
      // Close modal if it was open, since pipeline is updating data
      if (showWarningModal) {
        setShowWarningModal(false)
      }
      return
    }
    
    // Use backend freshness flags instead of manual age_days calculation
    const freshnessPolicy = dataStatus?.freshness_policy || 'strict'
    const hasRecentData = dataStatus?.has_recent_data === true
    const allowsStaleInputs = dataStatus?.allow_stale_inputs === true || freshnessPolicy === 'dev_allow_stale'
    
    // Only show warning if:
    // 1. Backend explicitly marks data as stale (has_recent_data=false AND freshness_policy=strict)
    // 2. OR metrics_status indicates problems (always show these warnings)
    const shouldShowWarning = 
      // Backend explicitly says data is stale (production mode with real stale data)
      (!hasRecentData && freshnessPolicy === 'strict') ||
      // Check if metrics_status indicates problems (always show these warnings)
      (metricsStatus && ['NO_TRADES', 'DEV_FALLBACK'].includes(metricsStatus))
    
    // Close modal automatically if data is now fresh according to backend
    const isDataFresh = 
      hasRecentData &&
      (metricsStatus === 'PASS' || !metricsStatus || !['NO_TRADES', 'DEV_FALLBACK'].includes(metricsStatus))
    
    if (isDataFresh && showWarningModal) {
      // Data is fresh according to backend, close modal
      setShowWarningModal(false)
    } else if (shouldShowWarning && !isPipelineRunning && !showWarningModal) {
      // Show modal only if pipeline is NOT running and conditions are met
      setShowWarningModal(true)
    }
  }, [dataStatus, metricsStatus, data, showWarningModal, isPipelineRunning])
  
  // Build warning message
  const warningMessage = useMemo(() => {
    const messages: string[] = []
    
    // If pipeline is running, show a different message
    if (isPipelineRunning) {
      return 'El pipeline está corriendo; los datos se actualizarán automáticamente'
    }
    
    // Use backend freshness flags instead of manual age calculation
    const freshnessPolicy = dataStatus?.freshness_policy || 'strict'
    const hasRecentData = dataStatus?.has_recent_data === true
    
    // Only show age warning if backend explicitly marks data as stale (production mode)
    // In dev mode (freshness_policy='dev_allow_stale'), the modal won't show, so this message won't appear
    if (!hasRecentData && freshnessPolicy === 'strict' && dataStatus?.latest_open_time) {
      const dateStr = dataStatus.latest_open_time_date || new Date(dataStatus.latest_open_time).toISOString().split('T')[0]
      const ageDays = dataStatus.age_days !== null ? Math.round(dataStatus.age_days) : 'N/A'
      messages.push(`Datos desactualizados: última vela ${dateStr} (hace ${ageDays} días)`)
    }
    
    if (metricsStatus === 'NO_TRADES') {
      messages.push('Sin trades simulados; revise diagnóstico')
    } else if (metricsStatus === 'DEV_FALLBACK') {
      messages.push('Modo desarrollo: métricas de respaldo')
    }
    
    return messages.join('. ')
  }, [dataStatus, metricsStatus, isPipelineRunning])

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

  const isDegraded = (effectiveData as any)?._isDegraded === true || isDegradedStatus || shouldDeemphasizeKPIs
  const isDevFallback = (effectiveData as any)?._isDevFallback === true || (data as any)?.dev_fallback === true || metricsStatus === 'DEV_FALLBACK'
  
  // Build degraded message based on metrics_status with precise root cause
  const getDegradedMessage = () => {
    // Show precise root cause for NO_TRADES
    if (metricsStatus === 'NO_TRADES') {
      if (noTradeRootCause) {
        const rootCauseMessages: Record<string, string> = {
          'no_signals_generated': 'No se generaron señales durante el backtest. Esto puede indicar que las condiciones de la estrategia no se cumplieron.',
          'no_enter_signals': 'Se generaron señales pero ninguna fue de entrada. La estrategia puede estar en estado de espera.',
          'invalid_stop_loss': 'Se generaron señales de entrada pero la configuración de stop loss es inválida (distancia cero o faltante).',
          'enter_signals_zero_size': `Se generaron ${noTradeDiagnostics?.signal_counts?.enter || 0} señales de entrada pero el sizing calculó tamaño cero. Puede indicar capital insuficiente, límites de riesgo, o distancias de stop loss inválidas.`,
          'orders_rejected': `Se generaron señales de entrada pero ${noTradeDiagnostics?.rejected_orders_count || 0} órdenes fueron rechazadas por el simulador de ejecución (profundidad insuficiente, precio movido, etc.).`,
          'unknown': 'Se generaron señales de entrada pero no se ejecutaron trades. Causa desconocida - revisar logs del backtest.',
        }
        return rootCauseMessages[noTradeRootCause] || noTradeDiagnostics?.reason || 'Sin trades ejecutados durante el backtest.'
      }
      return noTradeDiagnostics?.reason || 'Backtest invalid or incomplete (0 trades). Use this dashboard only as research, NOT as trading advice.'
    }
    if (metricsStatus === 'INSUFFICIENT_DATA') {
      return `Backtest invalid or incomplete (${tradeCount || 0} trades, below minimum). Use this dashboard only as research, NOT as trading advice.`
    }
    if (metricsStatus === 'DEV_FALLBACK') {
      return `Development mode: Fallback metrics (${tradeCount || 0} trades < 50). Backtest invalid or incomplete. Use this dashboard only as research, NOT as trading advice.`
    }
    if (metricsStatus === 'FAIL') {
      return 'Backtest validation failed. Backtest invalid or incomplete. Use this dashboard only as research, NOT as trading advice.'
    }
    if (metricsStatus === 'CACHE_MISS') {
      return 'Cache miss: Los datos del backtest se están calculando en segundo plano. Las métricas reales estarán disponibles pronto.'
    }
    if (cacheMiss) {
      return 'Cache miss: Los datos del backtest se están calculando en segundo plano. Las métricas reales estarán disponibles pronto.'
    }
    if (isDemoMetrics) {
      return 'Mostrando métricas demo. Los datos reales se están calculando en segundo plano.'
    }
    if (isDevFallback) {
      return 'Modo desarrollo: Mostrando métricas de respaldo generadas automáticamente.'
    }
    // Use degraded_reason if available for more precise messaging
    if (degradedReason) {
      const reasonMessages: Record<string, string> = {
        'cache_miss_cache_miss': 'Cache miss: Los datos del backtest se están calculando en segundo plano.',
        'cache_miss_warmup_failed': 'El cálculo del backtest falló. Intente nuevamente o revise los logs.',
        'no_trades_executed_no_signals_generated': 'No se generaron señales durante el backtest.',
        'no_trades_executed_no_enter_signals': 'Se generaron señales pero ninguna fue de entrada.',
        'no_trades_executed_invalid_stop_loss': 'Se generaron señales pero la configuración de stop loss es inválida.',
        'no_trades_executed_enter_signals_zero_size': 'Se generaron señales de entrada pero el sizing calculó tamaño cero.',
        'no_trades_executed_orders_rejected': 'Se generaron señales pero las órdenes fueron rechazadas.',
        'no_trades_executed_unknown': 'Sin trades ejecutados - causa desconocida.',
      }
      return reasonMessages[degradedReason] || (effectiveData as any)?._degradedMessage || data?.message || fallbackReason || 'Backtest invalid or incomplete. Use this dashboard only as research, NOT as trading advice.'
    }
    return (effectiveData as any)?._degradedMessage || data?.message || fallbackReason || 'Backtest invalid or incomplete. Use this dashboard only as research, NOT as trading advice.'
  }
  
  const degradedMessage = getDegradedMessage()

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
      
      {/* Pipeline Running Banner - Show when pipeline is active */}
      {isPipelineRunning && (
        <div 
          className="pipeline-running-banner" 
          role="status" 
          aria-live="polite"
          style={{
            padding: '1rem',
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            border: '1px solid rgba(59, 130, 246, 0.3)',
            borderRadius: '0.5rem',
            marginBottom: '1rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '1.25rem' }}>🔄</span>
            <div style={{ flex: 1 }}>
              <p style={{ margin: 0, fontWeight: 600, color: '#3b82f6' }}>
                Pipeline en ejecución
              </p>
              <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.875rem', color: 'rgba(255, 255, 255, 0.8)' }}>
                El pipeline está corriendo; los datos se actualizarán automáticamente cuando termine.
              </p>
              {pipelineStatus?.pipeline?.started_at && (
                <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.75rem', color: 'rgba(255, 255, 255, 0.6)', fontStyle: 'italic' }}>
                  Iniciado: {new Date(pipelineStatus.pipeline.started_at).toLocaleString()}
                </p>
              )}
            </div>
          </div>
        </div>
      )}
      
      {/* Warning Modal - Only show when pipeline is NOT running */}
      {showWarningModal && warningMessage && !isPipelineRunning && (
        <div 
          className="warning-modal-overlay" 
          onClick={() => setShowWarningModal(false)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div 
            className="warning-modal" 
            onClick={(e) => e.stopPropagation()}
            style={{
              backgroundColor: '#1f2937',
              border: '2px solid #ef4444',
              borderRadius: '0.5rem',
              padding: '1.5rem',
              maxWidth: '500px',
              width: '90%',
              boxShadow: '0 10px 25px rgba(0, 0, 0, 0.5)',
            }}
          >
            <h3 style={{ margin: '0 0 1rem 0', color: '#ef4444', fontSize: '1.25rem' }}>
              ⚠️ Advertencia
            </h3>
            <p style={{ margin: '0 0 1rem 0', color: 'rgba(255, 255, 255, 0.9)', lineHeight: '1.5' }}>
              {warningMessage}
            </p>
            {dataStatus?.latest_open_time && (
              <p style={{ margin: '0 0 1rem 0', fontSize: '0.875rem', color: 'rgba(255, 255, 255, 0.7)' }}>
                Última vela: {dataStatus.latest_open_time_date || new Date(dataStatus.latest_open_time).toISOString().split('T')[0]}
              </p>
            )}
            {(data as any)?.no_trade_diagnostics && (
              <div style={{ margin: '0 0 1rem 0', fontSize: '0.875rem', color: 'rgba(255, 255, 255, 0.7)' }}>
                <p style={{ margin: '0 0 0.5rem 0', fontWeight: 600 }}>Diagnóstico:</p>
                <p style={{ margin: 0 }}>
                  {(data as any).no_trade_diagnostics.reason || 'Sin trades ejecutados durante el backtest'}
                </p>
              </div>
            )}
            <button
              onClick={() => setShowWarningModal(false)}
              style={{
                padding: '0.5rem 1rem',
                backgroundColor: '#ef4444',
                color: 'white',
                border: 'none',
                borderRadius: '0.375rem',
                cursor: 'pointer',
                fontWeight: 500,
                fontSize: '0.875rem',
              }}
            >
              Entendido
            </button>
          </div>
        </div>
      )}
      
          {(isDegraded || shouldDeemphasizeKPIs) && (
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
              {noTradeRootCause && metricsStatus === 'NO_TRADES' && (
                <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.75rem', fontStyle: 'italic', color: 'rgba(255, 255, 255, 0.6)' }}>
                  Causa raíz: {noTradeRootCause}
                </p>
              )}
              {cacheMiss && (
                <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.75rem', fontStyle: 'italic', color: 'rgba(255, 255, 255, 0.6)' }}>
                  Los datos del backtest se están calculando en segundo plano. Esta página se actualizará automáticamente cuando estén listos.
                </p>
              )}
              {isDevFallback && !cacheMiss && (
                <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.75rem', fontStyle: 'italic', color: 'rgba(255, 255, 255, 0.6)' }}>
                  Las métricas mostradas son valores de respaldo generados automáticamente en modo desarrollo. No reflejan resultados reales de backtesting.
                </p>
              )}
              {isDemoMetrics && !isDevFallback && !cacheMiss && (
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
          {shouldDeemphasizeKPIs && (
            <div className="metrics-degraded-warning" role="alert" aria-live="assertive" style={{
              padding: '1rem',
              backgroundColor: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: '0.5rem',
              marginBottom: '1rem',
            }}>
              <p style={{ margin: 0, fontWeight: 600, color: '#ef4444', fontSize: '0.875rem' }}>
                ⚠️ Backtest Invalid or Incomplete
              </p>
              <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.875rem', color: 'rgba(255, 255, 255, 0.9)' }}>
                {degradedMessage}
              </p>
              {fallbackReason && (
                <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.75rem', fontStyle: 'italic', color: 'rgba(255, 255, 255, 0.7)' }}>
                  Reason: {fallbackReason}
                </p>
              )}
              {devBypass && (
                <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.75rem', fontStyle: 'italic', color: 'rgba(255, 255, 255, 0.7)' }}>
                  Dev bypass: {devBypass}
                </p>
              )}
            </div>
          )}
          <div className="metrics-grid" style={shouldDeemphasizeKPIs ? {
            opacity: 0.6,
            filter: 'grayscale(20%)',
          } : undefined}>
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

