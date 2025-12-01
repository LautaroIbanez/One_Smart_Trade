import { useState, useMemo, useEffect, useRef, lazy, Suspense } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import RecommendationCard from '../components/RecommendationCard'
import HistoryExplorer from '../components/HistoryExplorer'
import IndicatorsPanel from '../components/IndicatorsPanel'
import RiskPanel from '../components/RiskPanel'
import { PriceLevelsChart } from '../components/PriceLevelsChart'
import AppLayout from '../components/AppLayout'
import { useTodayRecommendation, useMarketData } from '../api/hooks'
import { ErrorState } from '../components/shared/ErrorState'
import { LoadingState } from '../components/shared/LoadingState'
import { DegradedDataBanner } from '../components/shared/DegradedDataBanner'
import { DataStalenessIndicator } from '../components/shared/DataStalenessIndicator'
import { isProcessingError } from '../api/hooks'
import { isTradableRecommendation, getNonTradableMessage } from '../utils/recommendation'
import type { MarketPoint } from '@/types'
import './Dashboard.css'

// Lazy load heavy components to reduce initial bundle size and parallel API calls
const PerformanceSummary = lazy(() => import('../components/PerformanceSummary'))
const SignalCompliance = lazy(() => import('../features/performance/SignalCompliance'))
const MonthlyPerformance = lazy(() => import('../features/performance/MonthlyPerformance'))
const RealVsTheoretical = lazy(() => import('../features/performance/RealVsTheoretical').then(m => ({ default: m.RealVsTheoretical })))
const ObservabilityDashboard = lazy(() => import('../components/ObservabilityDashboard'))
const TransparencyDashboard = lazy(() => import('../components/TransparencyDashboard'))
const LivelihoodDashboard = lazy(() => import('../components/LivelihoodDashboard'))
const UserRiskPanel = lazy(() => import('../components/UserRiskPanel'))

interface RefreshToast {
  id: string
  type: 'success' | 'error'
  message: string
}

function Dashboard() {
  const queryClient = useQueryClient()
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [refreshProgress, setRefreshProgress] = useState<number>(0)
  const [toast, setToast] = useState<RefreshToast | null>(null)
  const toastTimeoutRef = useRef<number | null>(null)
  const { data, isLoading: isRecommendationLoading, error: recommendationError, refetch: refetchRecommendation } = useTodayRecommendation()
  // FE-DATA-04: Market data query is now decoupled from recommendation timestamp
  // The query key no longer includes recommendationTimestamp, allowing independent refresh
  // Market data will refresh every 60s independently via refetchInterval
  const { data: marketData, isLoading: isMarketLoading, error: marketError, refetch: refetchMarket } = useMarketData('1h', null, 200)
  
  // FE-DATA-04: Monitor market data as_of to detect when new candles arrive
  // Track previous as_of to detect changes - the query will automatically refetch via refetchInterval
  const marketAsOf = marketData?.metadata?.as_of

  // Auto-dismiss toast after 5 seconds
  useEffect(() => {
    if (toast) {
      if (toastTimeoutRef.current) {
        clearTimeout(toastTimeoutRef.current)
      }
      toastTimeoutRef.current = window.setTimeout(() => {
        setToast(null)
      }, 5000)
    }
    return () => {
      if (toastTimeoutRef.current) {
        clearTimeout(toastTimeoutRef.current)
      }
    }
  }, [toast])

  const handleRefresh = async () => {
    setIsRefreshing(true)
    setRefreshProgress(0)
    setToast(null)

    try {
      // Get all active queries that should be refetched
      // We'll refetch queries for all dashboard sections
      const queryKeys = [
        ['recommendation'],
        ['market'],
        ['performance'],
        ['observability'],
        ['user-risk-state'],
        ['analytics'],
        ['reading-history'],
        ['knowledge-article'],
      ]

      // Count total queries to track progress - initialize with explicit refetches
      // We always have at least 2 explicit refetches (recommendation and market)
      let totalQueries = 2 // Start with explicit refetches
      let completedQueries = 0

      // Count queries before refetching
      queryKeys.forEach((queryKey) => {
        const queries = queryClient.getQueriesData({ queryKey })
        totalQueries += queries.length
      })

      // Ensure totalQueries is never zero to avoid NaN
      if (totalQueries === 0) {
        totalQueries = 1 // Fallback to 1 to prevent division by zero
      }

      // Helper function to safely update progress
      const updateProgress = (completed: number, total: number) => {
        if (total > 0 && !isNaN(completed) && !isNaN(total)) {
          const progress = Math.min(100, Math.round((completed / total) * 100))
          if (!isNaN(progress) && progress >= 0 && progress <= 100) {
            setRefreshProgress(progress)
          }
        }
      }

      // Refetch all queries
      const refetchPromises = queryKeys.map(async (queryKey) => {
        const queries = queryClient.getQueriesData({ queryKey })
        
        return Promise.all(
          queries.map(async ([key]) => {
            try {
              await queryClient.refetchQueries({ queryKey: key as any, type: 'active' })
              completedQueries++
              updateProgress(completedQueries, totalQueries)
            } catch (err) {
              console.error(`Error refetching query ${String(key)}:`, err)
              // Still count as completed to avoid blocking progress
              completedQueries++
              updateProgress(completedQueries, totalQueries)
            }
          })
        )
      })

      // Also refetch explicit queries from hooks that we know are active
      // These are counted in totalQueries from the start
      // Invalidate both recommendation and market caches together to keep them in sync
      const explicitRefetches = [
        Promise.all([
          queryClient.invalidateQueries({ queryKey: ['recommendation', 'today'] }),
          queryClient.invalidateQueries({ queryKey: ['market'] }),
        ])
          .then(() => Promise.all([refetchRecommendation(), refetchMarket()]))
          .then(() => {
            completedQueries++
            updateProgress(completedQueries, totalQueries)
          })
          .catch(err => {
            console.error('Error refetching recommendation/market:', err)
            completedQueries++
            updateProgress(completedQueries, totalQueries)
          }),
      ]
      
      // Wait for both explicit refetches and query key refetches
      await Promise.all([...refetchPromises, ...explicitRefetches])
      
      // Ensure final progress is 100% and not NaN
      setRefreshProgress(100)
      setToast({
        id: Date.now().toString(),
        type: 'success',
        message: 'Datos actualizados correctamente',
      })
    } catch (err) {
      console.error('Error refreshing data:', err)
      setToast({
        id: Date.now().toString(),
        type: 'error',
        message: 'Error al actualizar algunos datos. Algunos paneles pueden mostrar información desactualizada.',
      })
      // Set progress to 100% even on error to allow UI to reset
      setRefreshProgress(100)
    } finally {
      setIsRefreshing(false)
      // Reset progress after a short delay
      setTimeout(() => setRefreshProgress(0), 500)
    }
  }
  
  const chartData = useMemo<MarketPoint[]>(() => {
    if (!marketData?.data || !Array.isArray(marketData.data)) return []
    // FE-CHART-01: Accept both timestamp and open_time, sort by timestamp
    // Filter out invalid entries before sorting - ensure no date-based filtering excludes recent candles
    const validData = marketData.data.filter((item: any) => {
      const hasTimestamp = item?.timestamp || item?.open_time
      const hasPrice = item?.close !== undefined || item?.price !== undefined
      // FE-CHART-01: Do not filter by date - include all valid candles from API
      // Only filter out entries missing required fields
      return hasTimestamp && hasPrice
    })
    if (validData.length === 0) return []
    
    // FE-CHART-01: Sort chronologically (oldest to newest) to ensure latest candle is last
    const sortedData = [...validData].sort((a, b) => {
      const timeA = a.timestamp ?? a.open_time ?? ''
      const timeB = b.timestamp ?? b.open_time ?? ''
      const dateA = new Date(timeA).getTime()
      const dateB = new Date(timeB).getTime()
      // Handle invalid dates by putting them at the end
      if (isNaN(dateA) && isNaN(dateB)) return 0
      if (isNaN(dateA)) return 1
      if (isNaN(dateB)) return -1
      return dateA - dateB
    })
    
    // FE-CHART-01: Use window from API response or default to showing last 80 candles for performance
    // This ensures the latest candle from API is always included in the chart
    // The slice(-80) takes the LAST 80 candles, which includes the most recent one
    // IMPORTANT: If API metadata says latest is newer than what we have, log a warning
    const displayWindow = 80 // Display window for chart performance (not a data filter)
    
    // FE-CHART-01: Before slicing, verify that sortedData contains the latest timestamp from API
    const apiLatestTimestamp = marketData?.metadata?.as_of
    if (apiLatestTimestamp && sortedData.length > 0) {
      const sortedLatest = sortedData[sortedData.length - 1]
      const sortedLatestTimestamp = sortedLatest.timestamp ?? sortedLatest.open_time
      const sortedLatestMs = sortedLatestTimestamp ? new Date(sortedLatestTimestamp).getTime() : null
      const apiLatestMs = new Date(apiLatestTimestamp).getTime()
      
      // If API says latest is newer than what we have in sortedData, the API is not returning all data
      if (sortedLatestMs && apiLatestMs > sortedLatestMs) {
        const daysDiff = (apiLatestMs - sortedLatestMs) / (1000 * 60 * 60 * 24)
        console.error('[FE-CHART-01] API metadata indicates newer data than received in response', {
          apiLatestTimestamp,
          apiLatestDate: new Date(apiLatestTimestamp).toISOString(),
          sortedLatestTimestamp,
          sortedLatestDate: sortedLatestTimestamp ? new Date(sortedLatestTimestamp).toISOString() : null,
          differenceDays: daysDiff,
          totalCandlesReceived: sortedData.length,
          action: 'Backend API is not returning all available candles. Check backend /api/v1/market/{interval} endpoint.',
        })
      }
    }
    
    const dataToDisplay = sortedData.slice(-displayWindow)
    
    // FE-CHART-01: Log latest candle timestamp for validation and warn if mismatch
    if (dataToDisplay.length > 0) {
      const latestCandle = dataToDisplay[dataToDisplay.length - 1]
      const latestTimestamp = latestCandle.timestamp ?? latestCandle.open_time
      const apiLatestTimestamp = marketData?.metadata?.as_of
      const latestTimestampMs = latestTimestamp ? new Date(latestTimestamp).getTime() : null
      const apiLatestTimestampMs = apiLatestTimestamp ? new Date(apiLatestTimestamp).getTime() : null
      const timestampsMatch = latestTimestamp === apiLatestTimestamp || 
        (latestTimestampMs && apiLatestTimestampMs && Math.abs(latestTimestampMs - apiLatestTimestampMs) < 60000) // Within 1 minute
      
      // FE-CHART-01: Log all timestamps to diagnose data mismatch
      const firstCandle = dataToDisplay[0]
      const firstTimestamp = firstCandle.timestamp ?? firstCandle.open_time
      const allTimestamps = sortedData.map((item: any) => ({
        timestamp: item.timestamp ?? item.open_time,
        date: item.timestamp ?? item.open_time ? new Date(item.timestamp ?? item.open_time).toISOString() : null,
      }))
      
      console.debug('[FE-CHART-01] Chart data prepared', {
        totalCandlesFromAPI: validData.length,
        candlesDisplayed: dataToDisplay.length,
        firstCandleTimestamp: firstTimestamp,
        latestCandleTimestamp: latestTimestamp,
        apiLatestTimestamp: apiLatestTimestamp,
        timestampsMatch,
        timeDifferenceMs: latestTimestampMs && apiLatestTimestampMs ? Math.abs(latestTimestampMs - apiLatestTimestampMs) : null,
        dateRange: {
          first: firstTimestamp ? new Date(firstTimestamp).toISOString() : null,
          last: latestTimestamp ? new Date(latestTimestamp).toISOString() : null,
          apiLatest: apiLatestTimestamp ? new Date(apiLatestTimestamp).toISOString() : null,
        },
        // Log first and last 3 timestamps from sorted data to verify ordering
        firstThreeTimestamps: allTimestamps.slice(0, 3).map(t => t.date),
        lastThreeTimestamps: allTimestamps.slice(-3).map(t => t.date),
      })
      
      // FE-CHART-01: Warn if latest candle doesn't match API latest (potential data loss)
      if (!timestampsMatch && apiLatestTimestamp) {
        const daysDifference = latestTimestampMs && apiLatestTimestampMs 
          ? Math.abs(latestTimestampMs - apiLatestTimestampMs) / (1000 * 60 * 60 * 24)
          : null
        console.error('[FE-CHART-01] Latest candle timestamp mismatch - API has newer data not shown in chart', {
          chartLatest: latestTimestamp,
          chartLatestDate: latestTimestamp ? new Date(latestTimestamp).toISOString() : null,
          apiLatest: apiLatestTimestamp,
          apiLatestDate: apiLatestTimestamp ? new Date(apiLatestTimestamp).toISOString() : null,
          differenceMs: latestTimestampMs && apiLatestTimestampMs ? Math.abs(latestTimestampMs - apiLatestTimestampMs) : null,
          differenceDays: daysDifference,
          totalCandlesFromAPI: validData.length,
          candlesDisplayed: dataToDisplay.length,
          displayWindow,
          // Check if API data contains the latest timestamp
          apiDataContainsLatest: validData.some((item: any) => {
            const itemTs = item.timestamp ?? item.open_time
            return itemTs === apiLatestTimestamp || 
              (itemTs && apiLatestTimestamp && new Date(itemTs).getTime() === new Date(apiLatestTimestamp).getTime())
          }),
        })
      }
    }
    
    return dataToDisplay.map((item: Record<string, unknown>, index, arr) => {
      const rawTime = item.timestamp ?? item.open_time
      const timestamp =
        typeof rawTime === 'string'
          ? rawTime
          : rawTime instanceof Date
          ? rawTime.toISOString()
          : String(rawTime ?? '')

      // FE-DATA-01: Backend now provides open, high, low, close - use direct values with safe fallbacks
      const open = Number(item.open ?? item.o ?? item.price ?? 0)
      const high = Number(item.high ?? item.h ?? open)
      const low = Number(item.low ?? item.l ?? open)
      const close = Number(item.close ?? item.c ?? item.price ?? open)
      const volume = Number(item.volume ?? item.v ?? 0)

      let projection: number | undefined
      if (index >= arr.length - 10) {
        const window = arr.slice(index - 4 < 0 ? 0 : index - 4, index + 1)
        const xs = window.map((_, i) => i)
        const ys = window.map((row) => Number(row.close ?? row.price ?? close))
        const n = xs.length
        if (n >= 3) {
          const meanX = xs.reduce((a, b) => a + b, 0) / n
          const meanY = ys.reduce((a, b) => a + b, 0) / n
          const slope =
            xs.reduce((acc, x, i) => acc + (x - meanX) * (ys[i] - meanY), 0) /
            xs.reduce((acc, x) => acc + (x - meanX) ** 2, 0)
          projection = close + slope
        }
      }

      return { timestamp, open, high, low, close, volume, projection }
    })
  }, [marketData])

  return (
    <AppLayout>
      <div className="dashboard">
        <header className="dashboard-header">
          <h1>One Smart Trade</h1>
          <div className="refresh-controls">
            <button
              onClick={handleRefresh}
              className={`refresh-button ${isRefreshing ? 'refreshing' : ''}`}
              aria-label="Refrescar datos"
              type="button"
              disabled={isRefreshing}
            >
              {isRefreshing ? (
                <>
                  <span className="refresh-spinner">🔄</span>
                  Refrescando... {refreshProgress > 0 && `(${refreshProgress}%)`}
                </>
              ) : (
                '🔄 Refrescar'
              )}
            </button>
            {isRefreshing && refreshProgress > 0 && !isNaN(refreshProgress) && (
              <div className="refresh-progress-bar">
                <div 
                  className="refresh-progress-fill" 
                  style={{ width: `${Math.max(0, Math.min(100, refreshProgress))}%` }}
                  role="progressbar"
                  aria-valuenow={Math.max(0, Math.min(100, refreshProgress))}
                  aria-valuemin={0}
                  aria-valuemax={100}
                />
              </div>
            )}
          </div>
        </header>
        {toast && (
          <div 
            className={`refresh-toast ${toast.type}`}
            role="alert"
            aria-live="polite"
            onClick={() => setToast(null)}
          >
            <span className="toast-icon">
              {toast.type === 'success' ? '✓' : '⚠️'}
            </span>
            <span className="toast-message">{toast.message}</span>
            <button 
              type="button" 
              className="toast-dismiss"
              aria-label="Cerrar notificación"
              onClick={(e) => {
                e.stopPropagation()
                setToast(null)
              }}
            >
              ×
            </button>
          </div>
        )}
        <main className="dashboard-content">
          <RecommendationCard />
          {/* Price Chart Section with Error/Loading Handling */}
          <section className="price-chart" aria-label="Gráfico de precio con niveles recomendados">
            <h2>Precio vs Niveles Recomendados</h2>
            {isRecommendationLoading || isMarketLoading ? (
              <LoadingState message="Cargando datos de mercado y recomendación..." />
            ) : (recommendationError || marketError) && !isProcessingError(recommendationError || marketError) ? (
              <ErrorState 
                error={recommendationError || marketError} 
                title="Error al cargar gráfico de precios"
                onRetry={() => {
                  if (recommendationError) refetchRecommendation()
                  if (marketError) {
                    queryClient.invalidateQueries({ queryKey: ['market', '1h'] }).then(() => refetchMarket())
                  }
                }}
              />
            ) : isProcessingError(recommendationError || marketError) ? (
              <div className="processing-state">
                <LoadingState message="El pipeline de datos se está ejecutando. Los datos del gráfico estarán disponibles en unos momentos..." />
                <DegradedDataBanner 
                  message="El backend está procesando datos. Esta página se actualizará automáticamente cuando los datos estén listos."
                />
                <button 
                  type="button"
                  onClick={() => {
                    if (recommendationError) refetchRecommendation()
                    if (marketError) {
                      queryClient.invalidateQueries({ queryKey: ['market', '1h'] }).then(() => refetchMarket())
                    }
                  }}
                  style={{ marginTop: '1rem' }}
                >
                  🔄 Reintentar ahora
                </button>
              </div>
            ) : data && isTradableRecommendation(data) && chartData.length > 0 ? (
              <>
                {data.metadata?.served_from_cache && (
                  <DegradedDataBanner 
                    message="Mostrando datos en caché. Los datos frescos se están actualizando en segundo plano."
                    source={data.metadata?.source}
                    cachedAt={data.metadata?.generated_at}
                  />
                )}
                {marketData?.metadata?.served_from_cache && (
                  <DegradedDataBanner 
                    message="Gráfico mostrando datos en caché. Los datos frescos se están actualizando en segundo plano."
                    source={marketData.metadata?.source}
                  />
                )}
                {marketData?.status === 'data_stale' && (
                  <DegradedDataBanner 
                    message={marketData.reason || "Los datos del gráfico están desactualizados. Por favor, actualiza manualmente."}
                    source={marketData.metadata?.source}
                  />
                )}
                {/* FE-DATA-04: Show age information when data is approaching stale */}
                {marketData?.metadata?.age_minutes && marketData.metadata.age_minutes > 30 && marketData.status !== 'data_stale' && (
                  <DegradedDataBanner 
                    message={`Datos del gráfico tienen ${Math.round(marketData.metadata.age_minutes)} minutos de antigüedad. Se actualizarán automáticamente cuando haya nuevas velas.`}
                  />
                )}
                {/* FE-UX-02: Display data staleness indicator near chart */}
                <DataStalenessIndicator
                  asOf={marketData?.metadata?.as_of}
                  ageMinutes={marketData?.metadata?.age_minutes}
                  isStale={marketData?.status === 'data_stale'}
                  status={marketData?.status}
                  interval="1h"
                />
                <PriceLevelsChart
                  data={chartData}
                  stopLoss={data.stop_loss_take_profit.stop_loss}
                  takeProfit={data.stop_loss_take_profit.take_profit}
                  entryRange={[data.entry_range.min, data.entry_range.max]}
                  currentPrice={data.current_price}
                  tpProbability={
                    typeof data.risk_metrics?.tp_probability === 'number'
                      ? data.risk_metrics.tp_probability
                      : undefined
                  }
                  asOf={marketData?.metadata?.as_of}
                  isStale={marketData?.status === 'data_stale'}
                />
              </>
            ) : data && !isTradableRecommendation(data) ? (
              <div className="empty-state">
                <p>⚠️ <strong>Señal no disponible</strong></p>
                <p>{getNonTradableMessage(data as Record<string, unknown>)}</p>
                {data.status === 'cooldown' && (data as any).cooldown_remaining_seconds && (
                  <p className="cooldown-info">
                    Tiempo restante: {Math.floor((data as any).cooldown_remaining_seconds / 60)} minutos
                  </p>
                )}
              </div>
            ) : marketData?.status === 'no_data' ? (
              <div className="empty-state">
                <p>⚠️ <strong>Datos de mercado no disponibles</strong></p>
                <p>No hay datos de mercado disponibles para el intervalo seleccionado. Esto puede ocurrir si:</p>
                <ul style={{ textAlign: 'left', marginTop: '0.5rem' }}>
                  <li>El pipeline de datos aún está ejecutándose</li>
                  <li>No hay datos históricos para este intervalo</li>
                  <li>Ocurrió un error al cargar los datos</li>
                </ul>
                <button 
                  type="button"
                  onClick={() => refetchMarket()}
                  style={{ marginTop: '1rem' }}
                >
                  🔄 Reintentar
                </button>
              </div>
            ) : chartData.length === 0 && marketData ? (
              <div className="empty-state">
                <p>⚠️ <strong>No hay datos de velas disponibles</strong></p>
                <p>Los datos de mercado fueron cargados pero no contienen velas para renderizar el gráfico.</p>
                {marketData.metadata?.age_minutes && (
                  <p style={{ fontSize: '0.875rem', marginTop: '0.5rem' }}>
                    Última actualización: hace {Math.round(marketData.metadata.age_minutes)} minutos
                  </p>
                )}
                <button 
                  type="button"
                  onClick={() => refetchMarket()}
                  style={{ marginTop: '1rem' }}
                >
                  🔄 Reintentar
                </button>
              </div>
            ) : (
              <div className="empty-state">
                <p>⚠️ <strong>No hay datos suficientes para renderizar el gráfico</strong></p>
                <p>Esperando datos de mercado y recomendación...</p>
                {!isRecommendationLoading && !isMarketLoading && (
                  <button 
                    type="button"
                    onClick={() => {
                      refetchRecommendation()
                      refetchMarket()
                    }}
                    style={{ marginTop: '1rem' }}
                  >
                    🔄 Reintentar
                  </button>
                )}
              </div>
            )}
          </section>
          <div className="dashboard-grid">
            <IndicatorsPanel />
            <RiskPanel risk={data?.risk_metrics} />
          </div>
          <HistoryExplorer defaultPageSize={25} />
          <Suspense fallback={<LoadingState message="Cargando panel de riesgo de usuario..." />}>
            <UserRiskPanel />
          </Suspense>
          <Suspense fallback={<LoadingState message="Cargando resumen de rendimiento..." />}>
            <PerformanceSummary />
          </Suspense>
          <Suspense fallback={<LoadingState message="Cargando análisis de rendimiento..." />}>
            <RealVsTheoretical />
          </Suspense>
          <Suspense fallback={<LoadingState message="Cargando cumplimiento de señales..." />}>
            <SignalCompliance />
          </Suspense>
          <Suspense fallback={<LoadingState message="Cargando rendimiento mensual..." />}>
            <MonthlyPerformance />
          </Suspense>
          <Suspense fallback={<LoadingState message="Cargando análisis de subsistencia..." />}>
            <LivelihoodDashboard />
          </Suspense>
          <Suspense fallback={<LoadingState message="Cargando dashboard de observabilidad..." />}>
            <ObservabilityDashboard isPrivate={false} />
          </Suspense>
          <Suspense fallback={<LoadingState message="Cargando dashboard de transparencia..." />}>
            <TransparencyDashboard />
          </Suspense>
        </main>
      </div>
    </AppLayout>
  )
}

export default Dashboard

