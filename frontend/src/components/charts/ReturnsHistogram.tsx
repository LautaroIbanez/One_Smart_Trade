import { useMemo } from 'react'
import { Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar, ReferenceLine } from 'recharts'
import './ReturnsHistogram.css'

interface ChartDataPoint {
  date: Date
  return: number
  outcome: string
  signal: string
}

interface ReturnsHistogramProps {
  data: ChartDataPoint[]
}

export function ReturnsHistogram({ data }: ReturnsHistogramProps) {
  const histogramData = useMemo(() => {
    const bins: Record<string, number> = {}
    const binSize = 5

    data.forEach((point) => {
      const bin = Math.floor(point.return / binSize) * binSize
      const binKey = `${bin}`
      bins[binKey] = (bins[binKey] || 0) + 1
    })

    const result = Object.entries(bins)
      .map(([bin, count]) => ({
        range: `${bin}%`,
        count,
        value: Number(bin),
      }))
      .sort((a, b) => a.value - b.value)

    return result
  }, [data])

  const stats = useMemo(() => {
    if (data.length === 0) return { mean: 0, median: 0, std: 0 }

    const returns = data.map((d) => d.return)
    const mean = returns.reduce((a, b) => a + b, 0) / returns.length
    const sorted = [...returns].sort((a, b) => a - b)
    const median = sorted[Math.floor(sorted.length / 2)]
    const variance = returns.reduce((acc, r) => acc + Math.pow(r - mean, 2), 0) / returns.length
    const std = Math.sqrt(variance)

    return { mean, median, std }
  }, [data])

  if (histogramData.length === 0) {
    return <div className="chart-empty">No hay datos suficientes para mostrar el histograma</div>
  }

  const getColor = (value: number) => {
    if (value > 0) return '#10b981'
    if (value < 0) return '#ef4444'
    return '#6b7280'
  }

  return (
    <div className="returns-histogram">
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={histogramData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
          <XAxis dataKey="range" />
          <YAxis label={{ value: 'Frecuencia', angle: -90, position: 'insideLeft' }} />
          <Tooltip
            formatter={(value: number) => [value, 'Número de trades']}
            labelFormatter={(label) => `Retorno: ${label}`}
          />
          <ReferenceLine x="0%" stroke="#6b7280" strokeDasharray="3 3" />
          <Bar dataKey="count" radius={[8, 8, 0, 0]}>
            {histogramData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={getColor(entry.value)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="histogram-stats">
        <div className="stat-item">
          <span className="stat-label">Media:</span>
          <span className={`stat-value ${stats.mean >= 0 ? 'positive' : 'negative'}`}>
            {stats.mean >= 0 ? '+' : ''}
            {stats.mean.toFixed(2)}%
          </span>
        </div>
        <div className="stat-item">
          <span className="stat-label">Mediana:</span>
          <span className={`stat-value ${stats.median >= 0 ? 'positive' : 'negative'}`}>
            {stats.median >= 0 ? '+' : ''}
            {stats.median.toFixed(2)}%
          </span>
        </div>
        <div className="stat-item">
          <span className="stat-label">Desv. Est.:</span>
          <span className="stat-value">{stats.std.toFixed(2)}%</span>
        </div>
      </div>
    </div>
  )
}

