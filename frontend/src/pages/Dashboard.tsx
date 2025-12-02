import { useState, useEffect, useRef, lazy, Suspense } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import RecommendationCard from '../components/RecommendationCard'
import HistoryExplorer from '../components/HistoryExplorer'
import IndicatorsPanel from '../components/IndicatorsPanel'
import RiskPanel from '../components/RiskPanel'
import { NewMarketChart } from '../components/NewMarketChart'
import AppLayout from '../components/AppLayout'
import { useTodayRecommendation, useMarketData } from '../api/hooks'
import { ErrorState } from '../components/shared/ErrorState'
import { LoadingState } from '../components/shared/LoadingState'
import { DegradedDataBanner } from '../components/shared/DegradedDataBanner'
import { DataStalenessIndicator } from '../components/shared/DataStalenessIndicator'
import { isProcessingError } from '../api/hooks'
import { isTradableRecommendation, getNonTradableMessage } from '../utils/recommendation'
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

type ChartInterval = '1h' | '4h' | '1d'

function Dashboard() {
  const queryClient = useQueryClient()
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [refreshProgress, setRefreshProgress] = useState<number>(0)
  const [toast, setToast] = useState<RefreshToast | null>(null)
  const toastTimeoutRef = useRef<number | null>(null)
  // FE-CHART-01: Add interval selector state
  const [selectedInterval, setSelectedInterval] = useState<ChartInterval>('1h')
  const { data, isLoading: isRecommendationLoading, error: recommendationError, refetch: refetchRecommendation } = useTodayRecommendation()
  // FE-CHART-01: Use selected interval instead of hardcoded '1h'
  // FE-DATA-04: Market data query is now decoupled from recommendation timestamp
  // The query key no longer includes recommendationTimestamp, allowing independent refresh
  // Market data will refresh every 60s independently via refetchInterval
  const { data: marketData, isLoading: isMarketLoading, error: marketError, refetch: refetchMarket } = useMarketData(selectedInterval, null, 200)
  

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
          {/* FE-CHART-02: New Market Chart Section */}
          <section className="price-chart" aria-label="Gráfico de mercado con datos OHLC">
            <div className="price-chart-header">
              <h2>Gráfico de Mercado</h2>
              {/* FE-CHART-02: Interval selector */}
              <div className="interval-selector" role="group" aria-label="Seleccionar intervalo de tiempo">
                <button
                  type="button"
                  className={`interval-button ${selectedInterval === '1h' ? 'active' : ''}`}
                  onClick={() => setSelectedInterval('1h')}
                  aria-pressed={selectedInterval === '1h'}
                  aria-label="Intervalo de 1 hora"
                >
                  1h
                </button>
                <button
                  type="button"
                  className={`interval-button ${selectedInterval === '4h' ? 'active' : ''}`}
                  onClick={() => setSelectedInterval('4h')}
                  aria-pressed={selectedInterval === '4h'}
                  aria-label="Intervalo de 4 horas"
                >
                  4h
                </button>
                <button
                  type="button"
                  className={`interval-button ${selectedInterval === '1d' ? 'active' : ''}`}
                  onClick={() => setSelectedInterval('1d')}
                  aria-pressed={selectedInterval === '1d'}
                  aria-label="Intervalo de 1 día"
                >
                  1d
                </button>
              </div>
            </div>
            {/* FE-CHART-02: NewMarketChart handles all states internally */}
            <NewMarketChart interval={selectedInterval} window={200} />
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

