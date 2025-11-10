import { useMemo } from 'react'
import {
  ComposedChart,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  CartesianGrid,
  ReferenceLine,
  ReferenceArea,
  Line,
  ResponsiveContainer,
  Bar,
  Scatter,
  ScatterChart,
  ZAxis,
} from 'recharts'
import type { MarketPoint } from '@/types'

type Props = {
  data: MarketPoint[]
  stopLoss: number
  takeProfit: number
  entryRange: [number, number]
  currentPrice: number
  tpProbability?: number
}

type AnchorPoint = {
  timestamp: string
  price: number
}

const formatCurrency = (value: number) =>
  value.toLocaleString('es-ES', {
    style: 'currency',
    currency: 'USD',
  })

const formatTimestamp = (value: string | number | Date) => {
  const date = value instanceof Date ? value : new Date(value)
  return date.toLocaleString('es-ES', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const buildAnchorPoints = (points: MarketPoint[]): AnchorPoint[] => {
  const anchors: AnchorPoint[] = []
  let lastDate: string | null = null
  points.forEach((point) => {
    const timestamp = point.timestamp ?? ''
    if (typeof timestamp !== 'string') return
    const iso = timestamp.slice(0, 10)
    if (!iso || iso === lastDate) return
    if (typeof point.close === 'number') {
      anchors.push({ timestamp, price: point.close })
      lastDate = iso
    }
  })
  return anchors
}

export function PriceLevelsChart({ data, stopLoss, takeProfit, entryRange, currentPrice, tpProbability }: Props) {
  const filteredData = useMemo(
    () =>
      data.filter(
        (point) =>
          typeof point.timestamp === 'string' &&
          typeof point.close === 'number' &&
          !Number.isNaN(point.close),
      ),
    [data],
  )

  const latestPoint = filteredData[filteredData.length - 1]
  const latestClose = latestPoint?.close ?? currentPrice
  const latestTimestamp = latestPoint?.timestamp ?? new Date().toISOString()

  const projectionValues = filteredData
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

  const yDomain = useMemo(() => {
    const values = [
      ...filteredData.map((point) => point.close),
      takeProfit,
      stopLoss,
      entryRange[0],
      entryRange[1],
      currentPrice,
    ].filter((v) => typeof v === 'number' && !Number.isNaN(v))

    const min = Math.min(...values)
    const max = Math.max(...values)
    const padding = (max - min) * 0.05 || min * 0.02 || 50
    return [Math.floor(min - padding), Math.ceil(max + padding)]
  }, [filteredData, takeProfit, stopLoss, entryRange, currentPrice])

  const anchorPoints = useMemo(() => buildAnchorPoints(filteredData), [filteredData])

  return (
    <div className="price-levels-chart">
      <ResponsiveContainer width="100%" height={340}>
        <ComposedChart data={filteredData}>
          <CartesianGrid strokeDasharray="2 4" stroke="#1f2937" opacity={0.25} />
          <XAxis
            dataKey="timestamp"
            stroke="#94a3b8"
            minTickGap={30}
            tickFormatter={(value) => formatTimestamp(value).replace(',', '')}
          />
          <YAxis
            yAxisId="price"
            stroke="#94a3b8"
            domain={yDomain as [number, number]}
            tickFormatter={(value) => value.toLocaleString('es-ES')}
          />
          <YAxis yAxisId="volume" orientation="right" stroke="#475569" hide />
          <Tooltip
            formatter={(value: number | undefined, name: string) => {
              if (typeof value !== 'number') return value
              return [`${formatCurrency(value)}`, name]
            }}
            labelFormatter={(label: string) => formatTimestamp(label)}
            contentStyle={{ background: '#0f172a', borderRadius: 8, border: '1px solid rgba(255,255,255,0.08)' }}
          />
          <Legend />

          <ReferenceArea
            yAxisId="price"
            y1={Math.min(...entryRange)}
            y2={Math.max(...entryRange)}
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

          <ReferenceLine
            yAxisId="price"
            y={stopLoss}
            stroke="#f87171"
            strokeDasharray="6 4"
            strokeWidth={2}
            label={{ value: `SL ${formatCurrency(stopLoss)}`, fill: '#f87171', position: 'right', fontSize: 12 }}
          />
          <ReferenceLine
            yAxisId="price"
            y={takeProfit}
            stroke="#22c55e"
            strokeDasharray="6 4"
            strokeWidth={2}
            label={{ value: `TP ${formatCurrency(takeProfit)}`, fill: '#22c55e', position: 'right', fontSize: 12 }}
          />

          <ReferenceLine
            yAxisId="price"
            y={currentPrice}
            stroke="#0ea5e9"
            strokeDasharray="8 5"
            strokeWidth={2.4}
            label={{ value: `Spot ${formatCurrency(currentPrice)}`, fill: '#38bdf8', position: 'right', fontSize: 12 }}
          />

          <Line
            yAxisId="price"
            type="monotone"
            dataKey="close"
            stroke="#38bdf8"
            strokeWidth={2.2}
            dot={{ r: 2.5, fill: '#bae6fd', stroke: '#0ea5e9', strokeWidth: 1.2 }}
            activeDot={{ r: 4.5, fill: '#0ea5e9', stroke: '#bae6fd', strokeWidth: 1.5 }}
            name="Close (1h)"
          />

          <Line
            yAxisId="price"
            type="monotone"
            dataKey="projection"
            stroke="#c084fc"
            strokeDasharray="5 4"
            strokeWidth={1.5}
            dot={false}
            name="Proyección"
          />

          <ScatterChart>
            <Scatter
              data={anchorPoints}
              fill="#f97316"
              yAxisId="price"
              shape="circle"
              name="Cierre diario"
            >
              <ZAxis type="number" range={[120, 120]} />
            </Scatter>
          </ScatterChart>

          <Bar
            yAxisId="volume"
            dataKey="volume"
            fill="rgba(100, 116, 139, 0.5)"
            barSize={8}
            name="Volumen"
          />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="price-levels-chart-footer">
        <p>
          Spot actual:{' '}
          <strong>{formatCurrency(currentPrice ?? latestClose)}</strong>
          {' — '}
          {formatTimestamp(latestTimestamp)}
        </p>
        {typeof tpProbability === 'number' && (
          <p>
            Probabilidad TP estimada: <strong>{tpProbability.toFixed(1)}%</strong>
          </p>
        )}
      </div>
    </div>
  )
}


