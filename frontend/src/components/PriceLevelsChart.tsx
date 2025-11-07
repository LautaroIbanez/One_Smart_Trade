import {
  Area,
  AreaChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { MarketPoint } from '@/types'

type Props = {
  data: MarketPoint[]
  stopLoss: number
  takeProfit: number
  entryRange: [number, number]
}

export function PriceLevelsChart({ data, stopLoss, takeProfit, entryRange }: Props) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data}>
        <defs>
          <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#10b981" stopOpacity={0.8} />
            <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis dataKey="timestamp" stroke="#94a3b8" />
        <YAxis stroke="#94a3b8" domain={['auto', 'auto']} />
        <Tooltip />
        <Area type="monotone" dataKey="price" stroke="#10b981" fill="url(#priceGradient)" />
        <Line type="monotone" dataKey={() => stopLoss} stroke="#f87171" strokeDasharray="6 6" />
        <Line type="monotone" dataKey={() => takeProfit} stroke="#60a5fa" strokeDasharray="6 6" />
        <Line type="monotone" dataKey={() => entryRange[0]} stroke="#facc15" strokeDasharray="3 3" />
        <Line type="monotone" dataKey={() => entryRange[1]} stroke="#facc15" strokeDasharray="3 3" />
      </AreaChart>
    </ResponsiveContainer>
  )
}


