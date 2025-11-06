import { useState, useMemo } from 'react'
import RecommendationCard from '../components/RecommendationCard'
import HistoryTable from '../components/HistoryTable'
import IndicatorsPanel from '../components/IndicatorsPanel'
import RiskPanel from '../components/RiskPanel'
import PriceLevelsChart from '../components/PriceLevelsChart'
import PerformanceSummary from '../components/PerformanceSummary'
import AppLayout from '../components/AppLayout'
import { useInvalidateAll, useTodayRecommendation, useMarketData } from '../api/hooks'
import './Dashboard.css'

function Dashboard() {
  const [refreshKey, setRefreshKey] = useState(0)
  const invalidateAll = useInvalidateAll()
  const { data } = useTodayRecommendation()

  const handleRefresh = async () => {
    await invalidateAll()
    setRefreshKey((prev) => prev + 1)
  }

  const { data: marketData } = useMarketData('1h')
  
  const levels = data
    ? {
        entry_min: data.entry_range?.min,
        entry_max: data.entry_range?.max,
        stop_loss: data.stop_loss_take_profit?.stop_loss,
        take_profit: data.stop_loss_take_profit?.take_profit,
      }
    : undefined

  const chartData = useMemo(() => {
    if (!marketData?.data || !Array.isArray(marketData.data)) return []
    return marketData.data.slice(-50).map((item: any) => ({
      open_time: new Date(item.open_time || item.timestamp).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }),
      close: item.close || item.current_price,
    }))
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
          >
            Refrescar
          </button>
        </header>
        <main className="dashboard-content">
          <RecommendationCard key={refreshKey} />
          <PriceLevelsChart data={chartData} levels={levels} />
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

