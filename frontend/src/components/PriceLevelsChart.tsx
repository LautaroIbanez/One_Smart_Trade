import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import './PriceLevelsChart.css'

type Candle = { open_time: string; close: number }

type Props = {
  data: Candle[]
  levels?: { entry_min?: number; entry_max?: number; stop_loss?: number; take_profit?: number }
}

export default function PriceLevelsChart({ data, levels }: Props) {
  return (
    <div className="levels-chart">
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ left: 16, right: 16, top: 8, bottom: 8 }}>
          <XAxis dataKey="open_time" hide tick={false} />
          <YAxis stroke="#777" domain={['auto', 'auto']} />
          <Tooltip labelFormatter={() => ''} />
          <Line type="monotone" dataKey="close" stroke="#3b82f6" dot={false} strokeWidth={2} />
          {levels?.entry_min && (
            <ReferenceLine y={levels.entry_min} stroke="#f59e0b" strokeDasharray="4 4" label="Entry min" />
          )}
          {levels?.entry_max && (
            <ReferenceLine y={levels.entry_max} stroke="#f59e0b" strokeDasharray="4 4" label="Entry max" />
          )}
          {levels?.stop_loss && (
            <ReferenceLine y={levels.stop_loss} stroke="#ef4444" strokeDasharray="6 6" label="SL" />
          )}
          {levels?.take_profit && (
            <ReferenceLine y={levels.take_profit} stroke="#10b981" strokeDasharray="6 6" label="TP" />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}


