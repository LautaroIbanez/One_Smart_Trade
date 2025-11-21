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

  // Extract data from main payload or fallback_summary
  const effectiveData = useMemo(() => {
    if (!data) return null
    
    // If status is error but we have fallback_summary, use it
    if (data.status === 'error' && (data as any).fallback_summary) {
      const fallback = (data as any).fallback_summary
      return {
        ...data,
        // Merge fallback data into main payload for easier access
        equity_curve: (data as any).equity_curve || fallback.equity_curve || [],
        equity_theoretical: (data as any).equity_theoretical || fallback.equity_theoretical || [],
        equity_realistic: (data as any).equity_realistic || fallback.equity_realistic || [],
        tracking_error_rmse: (data as any).tracking_error_rmse || fallback.tracking_error_metrics?.rmse || null,
        tracking_error_max: (data as any).tracking_error_max || fallback.tracking_error?.max_divergence_bps || null,
        has_realistic_data: (data as any).has_realistic_data || Boolean(fallback.equity_realistic?.length),
        orderbook_fallback_events: (data as any).orderbook_fallback_events || null,
        _isDegraded: true,
        _degradedMessage: data.message || 'Datos en modo degradado',
      }
    }
    
    return data
  }, [data])

  const isDegraded = (effectiveData as any)?._isDegraded === true

  const equitySeries = useMemo(() => {
    if (!effectiveData) return []
    
    // Access equity data from API response (may come from fallback)
    const equity_curve = (effectiveData as any).equity_curve
    const equity_theoretical = (effectiveData as any).equity_theoretical
    const equity_realistic = (effectiveData as any).equity_realistic
    
    // Guard against empty arrays
    if (
      (!equity_curve || !Array.isArray(equity_curve) || equity_curve.length === 0) &&
      (!equity_theoretical || !Array.isArray(equity_theoretical) || equity_theoretical.length === 0) &&
      (!equity_realistic || !Array.isArray(equity_realistic) || equity_realistic.length === 0)
    ) {
      return []
    }
    
    return buildEquitySeries(
      equity_curve, // equity_curve DataFrame format
      equity_theoretical, // equity_theoretical array
      equity_realistic  // equity_realistic array
    )
  }, [effectiveData])

  const trackingErrorMetrics = useMemo(() => {
    if (!effectiveData) {
      return {
        rmse: null,
        max: null,
        hasRealisticData: false,
      }
    }
    
    return {
      rmse: (effectiveData as any).tracking_error_rmse ?? null,
      max: (effectiveData as any).tracking_error_max ?? null,
      hasRealisticData: (effectiveData as any).has_realistic_data ?? false,
      orderbookFallbackEvents: (effectiveData as any).orderbook_fallback_events ?? null,
    }
  }, [effectiveData])

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

  // Show degraded mode banner if using fallback data
  const degradedBanner = isDegraded ? (
    <div className="degraded-mode-banner" role="status" aria-live="polite">
      <p>⚠️ <strong>Modo degradado:</strong> {(effectiveData as any)?._degradedMessage || 'Mostrando datos almacenados en lugar de datos frescos.'}</p>
    </div>
  ) : null

  if (isError || (!effectiveData && !data)) {
    return (
      <section className="real-vs-theoretical" role="alert">
        <header>
          <h2>Ejecución Real vs. Teórica</h2>
        </header>
        <p>Error al cargar datos de ejecución.</p>
      </section>
    )
  }

  // If we have degraded data but no equity series, show placeholder
  if (isDegraded && equitySeries.length === 0) {
    return (
      <section className="real-vs-theoretical">
        <header>
          <h2>Ejecución Real vs. Teórica</h2>
        </header>
        {degradedBanner}
        <div className="no-data-placeholder">
          <p>⚠️ Datos de equity no disponibles en modo degradado</p>
          <p>Los datos frescos no están disponibles y no hay datos de equity almacenados para mostrar.</p>
          {trackingErrorMetrics.rmse !== null && (
            <div className="tracking-error-metrics">
              <div className="metric-item">
                <span className="metric-label">Tracking Error RMSE (degradado):</span>
                <span className="metric-value">{trackingErrorMetrics.rmse.toFixed(4)}</span>
              </div>
            </div>
          )}
        </div>
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
      {degradedBanner}

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

