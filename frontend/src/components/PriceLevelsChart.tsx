import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import './PriceLevelsChart.css'

type Candle = { open_time: string; close: number }

type Props = {
  data: Candle[]
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

export default function PriceLevelsChart({ data, levels, marketData }: Props) {
  if (!data || data.length === 0) {
    return (
      <div className="levels-chart" role="status" aria-live="polite">
        <h3>Precio vs Niveles Recomendados</h3>
        <div className="empty">Cargando datos de mercado...</div>
      </div>
    )
  }

  // Use market data support/resistance if available, otherwise use levels
  const support = marketData?.support || levels?.support
  const resistance = marketData?.resistance || levels?.resistance

  return (
    <div className="levels-chart" role="img" aria-label="Gráfico de precio con niveles de entrada, stop loss, take profit, soporte y resistencia">
      <h3>Precio vs Niveles Recomendados</h3>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data} margin={{ left: 16, right: 16, top: 8, bottom: 8 }}>
          <XAxis dataKey="open_time" stroke="#777" tick={{ fill: '#a0a0a0' }} />
          <YAxis stroke="#777" domain={['auto', 'auto']} tick={{ fill: '#a0a0a0' }} />
          <Tooltip
            contentStyle={{ backgroundColor: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', color: 'var(--text-primary)' }}
            labelFormatter={(label) => `Tiempo: ${label}`}
            formatter={(value: number) => [`$${value.toLocaleString()}`, 'Precio']}
          />
          <Line type="monotone" dataKey="close" stroke="#3b82f6" dot={false} strokeWidth={2} name="Precio" />
          
          {/* Support and Resistance from market data */}
          {support && (
            <ReferenceLine 
              y={support} 
              stroke="#8b5cf6" 
              strokeDasharray="3 3" 
              strokeWidth={1.5}
              label={{ value: 'Soporte', position: 'right', fill: '#8b5cf6' }} 
            />
          )}
          {resistance && (
            <ReferenceLine 
              y={resistance} 
              stroke="#8b5cf6" 
              strokeDasharray="3 3" 
              strokeWidth={1.5}
              label={{ value: 'Resistencia', position: 'right', fill: '#8b5cf6' }} 
            />
          )}
          
          {/* Entry levels */}
          {levels?.entry_min && (
            <ReferenceLine 
              y={levels.entry_min} 
              stroke="#f59e0b" 
              strokeDasharray="4 4" 
              strokeWidth={2}
              label={{ value: 'Entry min', position: 'right', fill: '#f59e0b' }} 
            />
          )}
          {levels?.entry_max && (
            <ReferenceLine 
              y={levels.entry_max} 
              stroke="#f59e0b" 
              strokeDasharray="4 4" 
              strokeWidth={2}
              label={{ value: 'Entry max', position: 'right', fill: '#f59e0b' }} 
            />
          )}
          
          {/* Stop Loss and Take Profit */}
          {levels?.stop_loss && (
            <ReferenceLine 
              y={levels.stop_loss} 
              stroke="#ef4444" 
              strokeDasharray="6 6" 
              strokeWidth={2}
              label={{ value: 'SL', position: 'right', fill: '#ef4444' }} 
            />
          )}
          {levels?.take_profit && (
            <ReferenceLine 
              y={levels.take_profit} 
              stroke="#10b981" 
              strokeDasharray="6 6" 
              strokeWidth={2}
              label={{ value: 'TP', position: 'right', fill: '#10b981' }} 
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}


