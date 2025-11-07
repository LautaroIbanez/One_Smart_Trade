import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts"
import type { MarketPoint } from "../types"
import './PriceLevelsChart.css'

interface Props {
  data: MarketPoint[]
  stopLoss?: number
  takeProfit?: number
  entryRange?: [number, number]
  levels?: { 
    entry_min?: number
    entry_max?: number
    stop_loss?: number
    take_profit?: number
    support?: number
    resistance?: number
  }
  marketData?: {
    support?: number
    resistance?: number
    current_price?: number
  }
}

export function PriceLevelsChart({ 
  data, 
  stopLoss, 
  takeProfit, 
  entryRange,
  levels,
}: Props) {
  // Transform data to match MarketPoint format if needed
  const chartData = data.map((point) => {
    const pointAny = point as unknown as Record<string, unknown>
    return {
      timestamp: point.timestamp || (pointAny.open_time as string) || '',
      price: point.price || (pointAny.close as number) || 0,
    }
  })

  // Use provided props or fall back to levels object
  const sl = stopLoss || levels?.stop_loss
  const tp = takeProfit || levels?.take_profit
  const entry = entryRange || (levels?.entry_min && levels?.entry_max ? [levels.entry_min, levels.entry_max] : undefined)

  if (!chartData || chartData.length === 0) {
    return (
      <div className="levels-chart" role="status" aria-live="polite">
        <h3>Precio vs Niveles Recomendados</h3>
        <div className="empty">Cargando datos de mercado...</div>
      </div>
    )
  }

  return (
    <div className="levels-chart" role="img" aria-label="Gráfico de precio con niveles de entrada, stop loss, take profit">
      <h3>Precio vs Niveles Recomendados</h3>
      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={chartData} margin={{ left: 16, right: 16, top: 8, bottom: 8 }}>
          <defs>
            <linearGradient id="price" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#10b981" stopOpacity={0.8} />
              <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="timestamp" stroke="#94a3b8" />
          <YAxis stroke="#94a3b8" domain={["auto", "auto"]} />
          <Tooltip
            contentStyle={{ backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
            labelFormatter={(label) => `Tiempo: ${label}`}
            formatter={(value: number) => [`$${value.toLocaleString()}`, 'Precio']}
          />
          <Area type="monotone" dataKey="price" stroke="#10b981" fill="url(#price)" />
          {sl && (
            <ReferenceLine 
              y={sl} 
              stroke="#f87171" 
              strokeDasharray="5 5" 
              label={{ value: 'SL', position: 'right', fill: '#f87171' }}
            />
          )}
          {tp && (
            <ReferenceLine 
              y={tp} 
              stroke="#60a5fa" 
              strokeDasharray="5 5" 
              label={{ value: 'TP', position: 'right', fill: '#60a5fa' }}
            />
          )}
          {entry && entry[0] && (
            <ReferenceLine 
              y={entry[0]} 
              stroke="#facc15" 
              strokeDasharray="3 3" 
              label={{ value: 'Entry min', position: 'right', fill: '#facc15' }}
            />
          )}
          {entry && entry[1] && (
            <ReferenceLine 
              y={entry[1]} 
              stroke="#facc15" 
              strokeDasharray="3 3" 
              label={{ value: 'Entry max', position: 'right', fill: '#facc15' }}
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

export default PriceLevelsChart


