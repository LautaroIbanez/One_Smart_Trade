import {
  ComposedChart,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  ReferenceArea,
  ReferenceLine,
  Bar,
  Line,
  ResponsiveContainer,
  Layer,
} from 'recharts'
import type { MarketPoint } from '@/types'

type Props = {
  data: MarketPoint[]
  stopLoss: number
  takeProfit: number
  entryRange: [number, number]
  tpProbability?: number
}

const CandleShape = (props: any) => {
  const { x, width, payload, yAxis } = props
  const scale = yAxis?.scale
  if (!scale || typeof payload !== 'object') return null

  const open = Number(payload.open ?? 0)
  const close = Number(payload.close ?? 0)
  const high = Number(payload.high ?? Math.max(open, close))
  const low = Number(payload.low ?? Math.min(open, close))

  const openY = scale(open)
  const closeY = scale(close)
  const highY = scale(high)
  const lowY = scale(low)

  const candleTop = Math.min(openY, closeY)
  const candleBottom = Math.max(openY, closeY)
  const candleHeight = Math.max(candleBottom - candleTop, 1)
  const wickX = x + width / 2

  const bullish = close >= open
  const fill = bullish ? '#34d399' : '#f87171'
  const stroke = bullish ? '#059669' : '#dc2626'

  return (
    <Layer>
      <line x1={wickX} x2={wickX} y1={highY} y2={lowY} stroke={stroke} strokeWidth={1} />
      <rect
        x={x + width * 0.18}
        y={candleTop}
        width={width * 0.64}
        height={candleHeight}
        fill={fill}
        stroke={stroke}
        rx={1}
      />
    </Layer>
  )
}

export function PriceLevelsChart({ data, stopLoss, takeProfit, entryRange, tpProbability }: Props) {
  const projectionValues = data
    .map((point) => point.projection)
    .filter((value): value is number => typeof value === 'number' && !Number.isNaN(value))
  const projectionBand =
    projectionValues.length > 0
      ? {
          lower: Math.min(...projectionValues),
          upper: Math.max(...projectionValues),
        }
      : null

  let projectionColor: string | null = null
  if (typeof tpProbability === 'number') {
    projectionColor =
      tpProbability > 60 ? '#22c55e' : tpProbability >= 40 ? '#f97316' : '#ef4444'
  }

  return (
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
        <XAxis dataKey="timestamp" stroke="#94a3b8" minTickGap={20} />
        <YAxis yAxisId="price" stroke="#94a3b8" domain={['auto', 'auto']} />
        <YAxis yAxisId="volume" orientation="right" stroke="#475569" hide />
        <Tooltip />
        <Legend />
        <ReferenceArea
          yAxisId="price"
          y1={entryRange[0]}
          y2={entryRange[1]}
          fill="#facc15"
          fillOpacity={0.12}
          strokeOpacity={0}
        />
        {projectionBand && projectionColor ? (
          <ReferenceArea
            yAxisId="price"
            y1={projectionBand.lower}
            y2={projectionBand.upper}
            fill={projectionColor}
            fillOpacity={0.12}
            strokeOpacity={0}
          />
        ) : null}
        <ReferenceLine yAxisId="price" y={stopLoss} stroke="#f87171" strokeDasharray="6 6" label="SL" />
        <ReferenceLine yAxisId="price" y={takeProfit} stroke="#60a5fa" strokeDasharray="6 6" label="TP" />
        <Bar yAxisId="price" dataKey="close" shape={CandleShape} isAnimationActive={false} barSize={10} />
        <Line
          yAxisId="price"
          type="monotone"
          dataKey="projection"
          stroke="#a855f7"
          strokeDasharray="4 4"
          dot={false}
          name="Proyección"
        />
        <Bar
          yAxisId="volume"
          dataKey="volume"
          fill="#64748b"
          opacity={0.6}
          barSize={8}
          name="Volumen"
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}


