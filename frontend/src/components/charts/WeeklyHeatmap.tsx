import { useMemo } from 'react'
import { format, getDay, startOfWeek } from 'date-fns'
import { Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts'
import './WeeklyHeatmap.css'

interface ChartDataPoint {
  date: Date
  return: number
  outcome: string
  signal: string
}

interface WeeklyHeatmapProps {
  data: ChartDataPoint[]
}

export function WeeklyHeatmap({ data }: WeeklyHeatmapProps) {
  const heatmapData = useMemo(() => {
    const weeks: Record<string, Record<number, { count: number; wins: number }>> = {}

    data.forEach((point) => {
      const weekStart = startOfWeek(point.date, { weekStartsOn: 1 })
      const weekKey = format(weekStart, 'yyyy-MM-dd')
      const dayOfWeek = getDay(point.date) === 0 ? 7 : getDay(point.date)

      if (!weeks[weekKey]) {
        weeks[weekKey] = {}
      }

      if (!weeks[weekKey][dayOfWeek]) {
        weeks[weekKey][dayOfWeek] = { count: 0, wins: 0 }
      }

      weeks[weekKey][dayOfWeek].count++
      if (point.outcome.toLowerCase().includes('tp') || point.outcome.toLowerCase().includes('profit')) {
        weeks[weekKey][dayOfWeek].wins++
      }
    })

    const result: Array<{ week: string; day: number; winRate: number; count: number }> = []

    Object.entries(weeks).forEach(([week, days]) => {
      Object.entries(days).forEach(([day, stats]) => {
        result.push({
          week,
          day: Number(day),
          winRate: stats.count > 0 ? (stats.wins / stats.count) * 100 : 0,
          count: stats.count,
        })
      })
    })

    return result.sort((a, b) => {
      if (a.week !== b.week) return a.week.localeCompare(b.week)
      return a.day - b.day
    })
  }, [data])

  const dayLabels = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']

  const chartData = useMemo(() => {
    const byDay: Record<number, { total: number; wins: number }> = {}
    dayLabels.forEach((_, index) => {
      byDay[index + 1] = { total: 0, wins: 0 }
    })

    heatmapData.forEach((item) => {
      byDay[item.day].total += item.count
      byDay[item.day].wins += item.count * (item.winRate / 100)
    })

    return dayLabels.map((label, index) => {
      const day = index + 1
      const stats = byDay[day]
      const winRate = stats.total > 0 ? (stats.wins / stats.total) * 100 : 0

      return {
        day: label,
        winRate,
        count: stats.total,
      }
    })
  }, [heatmapData, dayLabels])

  if (chartData.length === 0) {
    return <div className="chart-empty">No hay datos suficientes para mostrar el heatmap</div>
  }

  const getColor = (winRate: number) => {
    if (winRate >= 70) return '#10b981'
    if (winRate >= 50) return '#f59e0b'
    if (winRate >= 30) return '#ef4444'
    return '#6b7280'
  }

  return (
    <div className="weekly-heatmap">
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
          <XAxis dataKey="day" />
          <YAxis domain={[0, 100]} label={{ value: 'Win Rate (%)', angle: -90, position: 'insideLeft' }} />
          <Tooltip
            formatter={(value: number, name: string, props: any) => [
              `${value.toFixed(1)}% (${props.payload.count} trades)`,
              'Win Rate',
            ]}
          />
          <Bar dataKey="winRate" radius={[8, 8, 0, 0]}>
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={getColor(entry.winRate)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="heatmap-legend">
        <div className="legend-item">
          <span className="legend-color" style={{ backgroundColor: '#10b981' }}></span>
          <span>≥70%</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ backgroundColor: '#f59e0b' }}></span>
          <span>50-69%</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ backgroundColor: '#ef4444' }}></span>
          <span>30-49%</span>
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{ backgroundColor: '#6b7280' }}></span>
          <span>&lt;30%</span>
        </div>
      </div>
    </div>
  )
}

