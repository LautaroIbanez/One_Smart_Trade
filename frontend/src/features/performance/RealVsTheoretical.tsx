import { useMemo } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ReferenceLine, Area } from 'recharts'
import { usePerformanceSummary } from '../../api/hooks'
import './RealVsTheoretical.css'

const DIVERGENCE_THRESHOLD = 0.02 // 2%

interface EquityPoint {
  index: number
  theoretical: number
  realistic: number
  divergence_pct: number
  has_divergence: boolean
}

function buildEquitySeries(
  equity_curve: Array<{ timestamp?: string; equity_theoretical?: number; equity_realistic?: number; equity_divergence_pct?: number }> | undefined,
  equity_theoretical: number[] | undefined,
  equity_realistic: number[] | undefined
): EquityPoint[] {
  // Try to use equity_curve DataFrame format first
  if (equity_curve && Array.isArray(equity_curve) && equity_curve.length > 0) {
    return equity_curve.map((point, index) => {
      const theoretical = point.equity_theoretical ?? 0
      const realistic = point.equity_realistic ?? 0
      const divergence_pct = point.equity_divergence_pct ?? 0
      const has_divergence = Math.abs(divergence_pct) > DIVERGENCE_THRESHOLD * 100
      return { index, theoretical, realistic, divergence_pct, has_divergence }
    })
  }
  
  // Fallback to separate arrays
  if (equity_theoretical && equity_realistic) {
    const minLen = Math.min(equity_theoretical.length, equity_realistic.length)
    const series: EquityPoint[] = []
    
    for (let i = 0; i < minLen; i++) {
      const theoretical = equity_theoretical[i] || 0
      const realistic = equity_realistic[i] || 0
      const divergence_pct = theoretical > 0 ? ((realistic - theoretical) / theoretical) * 100 : 0
      const has_divergence = Math.abs(divergence_pct) > DIVERGENCE_THRESHOLD * 100
      series.push({ index: i, theoretical, realistic, divergence_pct, has_divergence })
    }
    
    return series
  }
  
  return []
}

export function RealVsTheoretical() {
  const { data, isLoading, isError } = usePerformanceSummary()

  const equitySeries = useMemo(() => {
    if (!data || data.status !== 'success') return []
    
    // Access equity data from API response
    const equity_curve = (data as any).equity_curve
    const equity_theoretical = (data as any).equity_theoretical
    const equity_realistic = (data as any).equity_realistic
    
    return buildEquitySeries(
      equity_curve, // equity_curve DataFrame format
      equity_theoretical, // equity_theoretical array
      equity_realistic  // equity_realistic array
    )
  }, [data])

  const trackingErrorMetrics = useMemo(() => {
    if (!data || data.status !== 'success') {
      return {
        rmse: null,
        max: null,
        hasRealisticData: false,
      }
    }
    
    return {
      rmse: data.tracking_error_rmse ?? null,
      max: data.tracking_error_max ?? null,
      hasRealisticData: data.has_realistic_data ?? false,
      orderbookFallbackEvents: data.orderbook_fallback_events ?? null,
    }
  }, [data])

  if (isLoading) {
    return (
      <section className="real-vs-theoretical" aria-busy="true">
        <header>
          <h2>Ejecución Real vs. Teórica</h2>
        </header>
        <p>Cargando datos de ejecución...</p>
      </section>
    )
  }

  if (isError || !data || data.status !== 'success') {
    return (
      <section className="real-vs-theoretical" role="alert">
        <header>
          <h2>Ejecución Real vs. Teórica</h2>
        </header>
        <p>Error al cargar datos de ejecución.</p>
      </section>
    )
  }

  // Show banner if no realistic data
  if (!trackingErrorMetrics.hasRealisticData) {
    return (
      <section className="real-vs-theoretical">
        <header>
          <h2>Ejecución Real vs. Teórica</h2>
        </header>
        <div className="no-data-banner">
          <p>⚠️ Sin datos realistas</p>
          <p>Este backtest no incluye datos de ejecución realista. Los resultados mostrados son teóricos únicamente.</p>
        </div>
      </section>
    )
  }

  // If no equity series available, show metrics only
  if (equitySeries.length === 0) {
    return (
      <section className="real-vs-theoretical">
        <header>
          <h2>Ejecución Real vs. Teórica</h2>
        </header>
        <div className="tracking-error-metrics">
          {trackingErrorMetrics.rmse !== null && (
            <div className="metric-item">
              <span className="metric-label">Tracking Error RMSE:</span>
              <span className="metric-value">{trackingErrorMetrics.rmse.toFixed(4)}</span>
            </div>
          )}
          {trackingErrorMetrics.max !== null && (
            <div className="metric-item">
              <span className="metric-label">Máxima Divergencia:</span>
              <span className="metric-value">{trackingErrorMetrics.max.toFixed(2)} bps</span>
            </div>
          )}
          {trackingErrorMetrics.orderbookFallbackEvents !== null && (
            <div className="metric-item">
              <span className="metric-label">Eventos de Fallback:</span>
              <span className="metric-value">{trackingErrorMetrics.orderbookFallbackEvents}</span>
            </div>
          )}
        </div>
      </section>
    )
  }

  return (
    <section className="real-vs-theoretical">
      <header>
        <h2>Ejecución Real vs. Teórica</h2>
      </header>

      <div className="tracking-error-metrics">
        {trackingErrorMetrics.rmse !== null && (
          <div className="metric-item">
            <span className="metric-label">Tracking Error RMSE:</span>
            <span className="metric-value">{trackingErrorMetrics.rmse.toFixed(4)}</span>
          </div>
        )}
        {trackingErrorMetrics.max !== null && (
          <div className="metric-item">
            <span className="metric-label">Máxima Divergencia:</span>
            <span className="metric-value">{trackingErrorMetrics.max.toFixed(2)} bps</span>
          </div>
        )}
        {trackingErrorMetrics.orderbookFallbackEvents !== null && (
          <div className="metric-item">
            <span className="metric-label">Eventos de Fallback:</span>
            <span className="metric-value">{trackingErrorMetrics.orderbookFallbackEvents}</span>
          </div>
        )}
      </div>

      <div className="equity-comparison-chart">
        <h3>Curvas de Equity: Teórica vs Realista</h3>
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={equitySeries} margin={{ top: 10, right: 30, left: 20, bottom: 20 }}>
            <defs>
              <linearGradient id="divergenceFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#ef4444" stopOpacity={0.0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255, 255, 255, 0.1)" />
            <XAxis 
              dataKey="index" 
              stroke="rgba(255, 255, 255, 0.6)"
              label={{ value: 'Bar #', position: 'insideBottom', offset: -10 }}
            />
            <YAxis 
              stroke="rgba(255, 255, 255, 0.6)"
              label={{ value: 'Capital ($)', angle: -90, position: 'insideLeft' }}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: 'rgba(16, 23, 39, 0.95)',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '8px',
                color: '#fff',
              }}
              formatter={(value: number, name: string, props: any) => {
                if (name === 'theoretical') return [`$${value.toFixed(2)}`, 'Equity Teórica']
                if (name === 'realistic') return [`$${value.toFixed(2)}`, 'Equity Realista']
                if (name === 'divergence_pct') return [`${value.toFixed(2)}%`, 'Divergencia']
                return [value, name]
              }}
              labelFormatter={(label) => `Bar ${label}`}
            />
            <Legend />
            <ReferenceLine y={equitySeries[0]?.theoretical || 0} stroke="rgba(255, 255, 255, 0.2)" strokeDasharray="2 2" />
            
            {/* Highlight divergences */}
            {equitySeries.map((point, idx) => {
              if (point.has_divergence) {
                return (
                  <ReferenceLine
                    key={`divergence-${idx}`}
                    x={point.index}
                    stroke="#ef4444"
                    strokeWidth={2}
                    strokeOpacity={0.5}
                  />
                )
              }
              return null
            })}
            
            <Area
              type="monotone"
              dataKey="realistic"
              stroke="none"
              fill="url(#divergenceFill)"
              fillOpacity={0.2}
            />
            <Line
              type="monotone"
              dataKey="theoretical"
              stroke="#1d4ed8"
              strokeWidth={2}
              dot={false}
              name="Equity Teórica"
              legendType="line"
            />
            <Line
              type="monotone"
              dataKey="realistic"
              stroke="#ef4444"
              strokeWidth={2}
              dot={false}
              name="Equity Realista"
              legendType="line"
            />
          </LineChart>
        </ResponsiveContainer>
        
        <div className="divergence-legend">
          <div className="legend-item">
            <span className="legend-color" style={{ backgroundColor: '#ef4444', opacity: 0.3 }}></span>
            <span>Divergencias &gt; {DIVERGENCE_THRESHOLD * 100}%</span>
          </div>
        </div>
      </div>
    </section>
  )
}

