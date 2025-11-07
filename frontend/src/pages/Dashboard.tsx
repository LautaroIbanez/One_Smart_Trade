import { useState, useMemo } from 'react'
import RecommendationCard from '../components/RecommendationCard'
import HistoryTable from '../components/HistoryTable'
import IndicatorsPanel from '../components/IndicatorsPanel'
import RiskPanel from '../components/RiskPanel'
import { PriceLevelsChart } from '../components/PriceLevelsChart'
import PerformanceSummary from '../components/PerformanceSummary'
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
    return marketData.data.slice(-50).map((item: Record<string, unknown>) => {
      const rawTime = item.timestamp ?? item.open_time
      const timestamp = typeof rawTime === 'string' ? rawTime : rawTime instanceof Date ? rawTime.toISOString() : String(rawTime ?? '')
      const price = typeof item.price === 'number' ? item.price : typeof item.close === 'number' ? item.close : typeof item.current_price === 'number' ? item.current_price : 0
      return {
        timestamp,
        price,
      }
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
          <HistoryTable />
          <PerformanceSummary />
        </main>
      </div>
    </AppLayout>
  )
}

export default Dashboard

