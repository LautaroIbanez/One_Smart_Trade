import { useState, useMemo, useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import RecommendationCard from '../components/RecommendationCard'
import HistoryExplorer from '../components/HistoryExplorer'
import IndicatorsPanel from '../components/IndicatorsPanel'
import RiskPanel from '../components/RiskPanel'
import { PriceLevelsChart } from '../components/PriceLevelsChart'
import PerformanceSummary from '../components/PerformanceSummary'
import SignalCompliance from '../features/performance/SignalCompliance'
import MonthlyPerformance from '../features/performance/MonthlyPerformance'
import { RealVsTheoretical } from '../features/performance/RealVsTheoretical'
import ObservabilityDashboard from '../components/ObservabilityDashboard'
import TransparencyDashboard from '../components/TransparencyDashboard'
import LivelihoodDashboard from '../components/LivelihoodDashboard'
import UserRiskPanel from '../components/UserRiskPanel'
import AppLayout from '../components/AppLayout'
import { useTodayRecommendation, useMarketData, isTimeoutError, getErrorMessage } from '../api/hooks'
import { ErrorState } from '../components/shared/ErrorState'
import { LoadingState } from '../components/shared/LoadingState'
import { DegradedDataBanner } from '../components/shared/DegradedDataBanner'
import type { MarketPoint } from '@/types'
import './Dashboard.css'

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

      // Count total queries to track progress
      let totalQueries = 0
      let completedQueries = 0

      // Refetch all queries
      const refetchPromises = queryKeys.map(async (queryKey) => {
        const queries = queryClient.getQueriesData({ queryKey })
        totalQueries += queries.length
        
        return Promise.all(
          queries.map(async ([key]) => {
            try {
              await queryClient.refetchQueries({ queryKey: key as any, type: 'active' })
              completedQueries++
              setRefreshProgress(Math.min(100, Math.round((completedQueries / totalQueries) * 100)))
            } catch (err) {
              console.error(`Error refetching query ${String(key)}:`, err)
              // Still count as completed to avoid blocking progress
              completedQueries++
              setRefreshProgress(Math.min(100, Math.round((completedQueries / totalQueries) * 100)))
            }
          })
        )
      })

      await Promise.all(refetchPromises)
      
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
            {isRefreshing && refreshProgress > 0 && (
              <div className="refresh-progress-bar">
                <div 
                  className="refresh-progress-fill" 
                  style={{ width: `${refreshProgress}%` }}
                  role="progressbar"
                  aria-valuenow={refreshProgress}
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
            ) : data && chartData.length > 0 ? (
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
          <UserRiskPanel />
          <PerformanceSummary />
          <RealVsTheoretical />
          <SignalCompliance />
          <MonthlyPerformance />
          <LivelihoodDashboard />
          <ObservabilityDashboard isPrivate={false} />
          <TransparencyDashboard />
        </main>
      </div>
    </AppLayout>
  )
}

export default Dashboard

