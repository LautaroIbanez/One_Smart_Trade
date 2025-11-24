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
  const { data: marketData, isLoading: isMarketLoading, error: marketError, refetch: refetchMarket } = useMarketData('1h')

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
      const explicitRefetches = [
        refetchRecommendation()
          .then(() => {
            completedQueries++
            updateProgress(completedQueries, totalQueries)
          })
          .catch(err => {
            console.error('Error refetching recommendation:', err)
            completedQueries++
            updateProgress(completedQueries, totalQueries)
          }),
        refetchMarket()
          .then(() => {
            completedQueries++
            updateProgress(completedQueries, totalQueries)
          })
          .catch(err => {
            console.error('Error refetching market:', err)
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
    return marketData.data.slice(-80).map((item: Record<string, unknown>, index, arr) => {
      const rawTime = item.timestamp ?? item.open_time
      const timestamp =
        typeof rawTime === 'string'
          ? rawTime
          : rawTime instanceof Date
          ? rawTime.toISOString()
          : String(rawTime ?? '')

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
            ) : recommendationError || marketError ? (
              <ErrorState 
                error={recommendationError || marketError} 
                title="Error al cargar gráfico de precios"
                onRetry={() => {
                  if (recommendationError) refetchRecommendation()
                  if (marketError) refetchMarket()
                }}
              />
            ) : data && isTradableRecommendation(data) && chartData.length > 0 ? (
              <>
                {data.metadata?.served_from_cache && (
                  <DegradedDataBanner 
                    message="Mostrando datos en caché. Los datos frescos se están actualizando en segundo plano."
                    source={data.metadata?.source}
                    cachedAt={data.metadata?.generated_at}
                  />
                )}
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
            ) : (
              <div className="empty-state">
                <p>⚠️ No hay datos suficientes para renderizar el gráfico.</p>
                <p>Esperando datos de mercado y recomendación...</p>
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

