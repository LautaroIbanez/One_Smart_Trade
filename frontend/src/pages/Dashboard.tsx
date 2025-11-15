import { useState, useMemo } from 'react'
import RecommendationCard from '../components/RecommendationCard'
import HistoryExplorer from '../components/HistoryExplorer'
import IndicatorsPanel from '../components/IndicatorsPanel'
import RiskPanel from '../components/RiskPanel'
import { PriceLevelsChart } from '../components/PriceLevelsChart'
import PerformanceSummary from '../components/PerformanceSummary'
import SignalCompliance from '../features/performance/SignalCompliance'
import MonthlyPerformance from '../features/performance/MonthlyPerformance'
import ObservabilityDashboard from '../components/ObservabilityDashboard'
import LivelihoodDashboard from '../components/LivelihoodDashboard'
import UserRiskPanel from '../components/UserRiskPanel'
import AppLayout from '../components/AppLayout'
import { useInvalidateAll, useTodayRecommendation, useMarketData } from '../api/hooks'
import type { MarketPoint } from '@/types'
import './Dashboard.css'

function Dashboard() {
  const [isRefreshing, setIsRefreshing] = useState(false)
  const invalidateAll = useInvalidateAll()
  const { data, refetch: refetchRecommendation } = useTodayRecommendation()
  const { data: marketData, refetch: refetchMarket } = useMarketData('1h')

  const handleRefresh = async () => {
    setIsRefreshing(true)
    try {
      // Invalidate all queries first
      await invalidateAll()
      // Then refetch all active queries
      await Promise.all([refetchRecommendation(), refetchMarket()])
    } catch (err) {
      console.error('Error refreshing data:', err)
    } finally {
      setIsRefreshing(false)
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
          <button
            onClick={handleRefresh}
            className="refresh-button"
            aria-label="Refrescar datos"
            type="button"
            disabled={isRefreshing}
          >
            {isRefreshing ? 'Refrescando...' : 'Refrescar'}
          </button>
        </header>
        <main className="dashboard-content">
          <RecommendationCard />
          {data && chartData.length > 0 ? (
            <section className="price-chart" aria-label="Gráfico de precio con niveles recomendados">
              <h2>Precio vs Niveles Recomendados</h2>
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
            </section>
          ) : (
            <section className="price-chart empty" aria-live="polite">
              <h2>Precio vs Niveles Recomendados</h2>
              <p>Esperando datos de mercado para renderizar el gráfico...</p>
            </section>
          )}
          <div className="dashboard-grid">
            <IndicatorsPanel />
            <RiskPanel risk={data?.risk_metrics} />
          </div>
          <HistoryExplorer defaultPageSize={25} />
          <UserRiskPanel />
          <PerformanceSummary />
          <SignalCompliance />
          <MonthlyPerformance />
          <LivelihoodDashboard enabled={(() => {
            const envFlag = (import.meta as any).env?.VITE_LIVELIHOOD_BETA === 'true'
            const lsFlag = localStorage.getItem('enableLivelihoodBeta') === 'true'
            return envFlag || lsFlag
          })()} />
          <ObservabilityDashboard isPrivate={false} />
        </main>
      </div>
    </AppLayout>
  )
}

export default Dashboard

