import { useState } from 'react'
import RecommendationCard from '../components/RecommendationCard'
import HistoryTable from '../components/HistoryTable'
import IndicatorsPanel from '../components/IndicatorsPanel'
import './Dashboard.css'

function Dashboard() {
  const [refreshKey, setRefreshKey] = useState(0)

  const handleRefresh = () => {
    setRefreshKey((prev) => prev + 1)
  }

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>One Smart Trade</h1>
        <button onClick={handleRefresh} className="refresh-button">
          Refrescar
        </button>
      </header>
      <main className="dashboard-content">
        <RecommendationCard key={refreshKey} />
        <div className="dashboard-grid">
          <IndicatorsPanel />
          <HistoryTable />
        </div>
      </main>
    </div>
  )
}

export default Dashboard

