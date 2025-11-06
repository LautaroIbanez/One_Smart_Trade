import { useState } from 'react'
import RecommendationCard from '../components/RecommendationCard'
import HistoryTable from '../components/HistoryTable'
import IndicatorsPanel from '../components/IndicatorsPanel'
import RiskPanel from '../components/RiskPanel'
import PriceLevelsChart from '../components/PriceLevelsChart'
import AppLayout from '../components/AppLayout'
import { useInvalidateAll, useTodayRecommendation } from '../api/hooks'
import './Dashboard.css'

function Dashboard() {
  const [refreshKey, setRefreshKey] = useState(0)
  const invalidateAll = useInvalidateAll()
  const { data } = useTodayRecommendation()

  const handleRefresh = async () => {
    await invalidateAll()
    setRefreshKey((prev) => prev + 1)
  }

  const levels = data
    ? {
        entry_min: data.entry_range?.min,
        entry_max: data.entry_range?.max,
        stop_loss: data.stop_loss_take_profit?.stop_loss,
        take_profit: data.stop_loss_take_profit?.take_profit,
      }
    : undefined

  // Mock small series for chart if no market endpoint shaping yet
  const series = [] as { open_time: string; close: number }[]

  return (
    <AppLayout>
      <div className="dashboard">
        <header className="dashboard-header">
          <h1>One Smart Trade</h1>
          <button onClick={handleRefresh} className="refresh-button" aria-label="Refrescar datos">
            Refrescar
          </button>
        </header>
        <main className="dashboard-content">
          <RecommendationCard key={refreshKey} />
          <PriceLevelsChart data={series} levels={levels} />
          <div className="dashboard-grid">
            <IndicatorsPanel />
            <RiskPanel risk={data?.risk_metrics} />
          </div>
          <HistoryTable />
        </main>
      </div>
    </AppLayout>
  )
}

export default Dashboard

