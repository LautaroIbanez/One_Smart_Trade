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
  Cell,
} from 'recharts'
import { useMarketData, useTodayRecommendation } from '../api/hooks'
import { ErrorState } from './shared/ErrorState'
import { LoadingState } from './shared/LoadingState'
import { DegradedDataBanner } from './shared/DegradedDataBanner'
import { DataStalenessIndicator } from './shared/DataStalenessIndicator'
import { isProcessingError } from '../api/hooks'
import type { MarketPoint } from '@/types'
import './NewMarketChart.css'

type ChartInterval = '1h' | '4h' | '1d'

interface NewMarketChartProps {
  interval?: ChartInterval
  window?: number
}

type CandleData = MarketPoint & {
  isUp: boolean
  candleHigh: number
  candleLow: number
}

const formatCurrency = (value: number) =>
  value.toLocaleString('es-ES', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
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

export function NewMarketChart({ interval = '1h', window = 200 }: NewMarketChartProps) {
  const { data: marketData, isLoading: isMarketLoading, error: marketError, refetch: refetchMarket, isRefetching } = useMarketData(interval, null, window)
  const { data: recommendationData } = useTodayRecommendation()

  // FE-CHART-02: Prepare candle data with OHLC structure
  const candleData = useMemo<CandleData[]>(() => {
    if (!marketData?.data || !Array.isArray(marketData.data)) return []
    
    const validData = marketData.data.filter((item: any) => {
      const hasTimestamp = item?.timestamp || item?.open_time
      const hasOHLC = item?.open !== undefined && item?.high !== undefined && item?.low !== undefined && item?.close !== undefined
      return hasTimestamp && hasOHLC
    })
    
    if (validData.length === 0) return []
    
    // Sort chronologically
    const sortedData = [...validData].sort((a, b) => {
      const timeA = a.timestamp ?? a.open_time ?? ''
      const timeB = b.timestamp ?? b.open_time ?? ''
      const dateA = new Date(timeA).getTime()
      const dateB = new Date(timeB).getTime()
      if (isNaN(dateA) && isNaN(dateB)) return 0
      if (isNaN(dateA)) return 1
      if (isNaN(dateB)) return -1
      return dateA - dateB
    })
    
    return sortedData.map((item: any) => {
      const open = Number(item.open ?? 0)
      const high = Number(item.high ?? open)
      const low = Number(item.low ?? open)
      const close = Number(item.close ?? open)
      const isUp = close >= open
      
      return {
        timestamp: item.timestamp ?? item.open_time ?? '',
        open,
        high,
        low,
        close,
        volume: Number(item.volume ?? item.v ?? 0),
        isUp,
        candleHigh: Math.max(open, close),
        candleLow: Math.min(open, close),
      }
    })
  }, [marketData])

  // FE-CHART-02: Verify latest candle timestamp matches metadata.as_of
  const latestCandle = candleData.length > 0 ? candleData[candleData.length - 1] : null
  const apiLatestTimestamp = marketData?.metadata?.as_of
  
  // FE-CHART-03: Check if as_of is valid
  const isAsOfValid = useMemo(() => {
    if (!apiLatestTimestamp) return false
    try {
      const date = new Date(apiLatestTimestamp)
      return !isNaN(date.getTime()) && date.getTime() > 0
    } catch {
      return false
    }
  }, [apiLatestTimestamp])
  
  // FE-CHART-04: Detect timestamp misalignment (as_of ahead of latest candle)
  const timestampMisalignment = useMemo(() => {
    if (!latestCandle || !apiLatestTimestamp || !isAsOfValid) return null
    const latestTimestamp = latestCandle.timestamp
    const latestTimestampMs = new Date(latestTimestamp).getTime()
    const apiLatestTimestampMs = new Date(apiLatestTimestamp).getTime()
    const diffMs = apiLatestTimestampMs - latestTimestampMs
    // If as_of is more than 1 minute ahead of latest candle, there's misalignment
    if (diffMs > 60000) {
      const diffMinutes = Math.floor(diffMs / (1000 * 60))
      const diffHours = Math.floor(diffMinutes / 60)
      const diffDays = Math.floor(diffHours / 24)
      let diffText = ''
      if (diffDays > 0) {
        diffText = `${diffDays} ${diffDays === 1 ? 'día' : 'días'}`
      } else if (diffHours > 0) {
        diffText = `${diffHours} ${diffHours === 1 ? 'hora' : 'horas'}`
      } else {
        diffText = `${diffMinutes} ${diffMinutes === 1 ? 'minuto' : 'minutos'}`
      }
      return {
        isAhead: true,
        diffMs,
        diffText,
        latestTimestamp,
        apiLatestTimestamp,
      }
    }
    return null
  }, [latestCandle, apiLatestTimestamp, isAsOfValid])
  
  const timestampsMatch = useMemo(() => {
    if (!latestCandle || !apiLatestTimestamp || !isAsOfValid) return false
    if (timestampMisalignment) return false
    const latestTimestamp = latestCandle.timestamp
    const latestTimestampMs = new Date(latestTimestamp).getTime()
    const apiLatestTimestampMs = new Date(apiLatestTimestamp).getTime()
    return Math.abs(latestTimestampMs - apiLatestTimestampMs) < 60000 // Within 1 minute
  }, [latestCandle, apiLatestTimestamp, isAsOfValid, timestampMisalignment])
  
  // FE-CHART-03: Determine if chart should be dimmed (invalid as_of or stale data)
  const shouldDimChart = useMemo(() => {
    return !isAsOfValid || isStale || (ageMinutes !== null && ageMinutes !== undefined && ageMinutes > 60)
  }, [isAsOfValid, isStale, ageMinutes])

  // FE-CHART-04: Determine chart state with better empty/error detection
  const chartState = useMemo<'loading' | 'success' | 'stale' | 'error' | 'empty'>(() => {
    if (isMarketLoading) return 'loading'
    if (marketError && !isProcessingError(marketError)) return 'error'
    if (marketData?.status === 'data_stale' || marketData?.metadata?.is_stale) return 'stale'
    if (marketData?.status === 'processing') return 'loading'
    // FE-CHART-04: Distinguish between empty data (no error) and actual error
    if (candleData.length === 0) {
      // If we have marketData but no candles, it's an empty state (not an error)
      if (marketData && !marketError) return 'empty'
      // If there's an error, it's an error state
      return 'error'
    }
    return 'success'
  }, [isMarketLoading, marketError, marketData, candleData.length])

  // FE-CHART-02: Check if data exceeds staleness threshold
  const ageMinutes = marketData?.metadata?.age_minutes
  const isStale = marketData?.status === 'data_stale' || marketData?.metadata?.is_stale || (ageMinutes !== null && ageMinutes !== undefined && ageMinutes > 60)
  const isStaleExceeded = ageMinutes !== null && ageMinutes !== undefined && ageMinutes > 60

  // FE-CHART-02: Get recommendation data for markers
  const stopLoss = recommendationData?.stop_loss_take_profit?.stop_loss
  const takeProfit = recommendationData?.stop_loss_take_profit?.take_profit
  const entryRange = recommendationData?.entry_range ? [recommendationData.entry_range.min, recommendationData.entry_range.max] as [number, number] : null
  const currentPrice = recommendationData?.current_price ?? marketData?.current_price ?? (latestCandle?.close ?? 0)

  // Calculate Y domain
  const yDomain = useMemo(() => {
    const values = [
      ...candleData.map((c) => c.high),
      ...candleData.map((c) => c.low),
    ]
    if (stopLoss) values.push(stopLoss)
    if (takeProfit) values.push(takeProfit)
    if (entryRange) {
      values.push(entryRange[0])
      values.push(entryRange[1])
    }
    values.push(currentPrice)
    
    const validValues = values.filter((v) => typeof v === 'number' && !Number.isNaN(v) && v > 0)
    if (validValues.length === 0) return [0, 100]
    
    const min = Math.min(...validValues)
    const max = Math.max(...validValues)
    const padding = (max - min) * 0.1 || min * 0.02 || 50
    return [Math.floor(min - padding), Math.ceil(max + padding)]
  }, [candleData, stopLoss, takeProfit, entryRange, currentPrice])

  // FE-CHART-02: Handle refresh button
  const handleRefresh = async () => {
    await refetchMarket()
  }

  // FE-CHART-02: Render states
  if (chartState === 'loading') {
    return (
      <div className="new-market-chart">
        <LoadingState message="Cargando datos de mercado..." />
      </div>
    )
  }

  // FE-CHART-04: Handle empty state (no candles but no error)
  if (chartState === 'empty') {
    return (
      <div className="new-market-chart">
        <div className="empty-chart-state">
          <div className="empty-state-icon">📊</div>
          <h3>No hay datos de velas disponibles</h3>
          <p>El endpoint devolvió una lista vacía. Esto puede ocurrir si:</p>
          <ul className="empty-state-reasons">
            <li>El pipeline de datos aún está ejecutándose</li>
            <li>No hay datos históricos para el intervalo seleccionado ({interval})</li>
            <li>El rango de fechas solicitado no contiene velas</li>
          </ul>
          {marketData?.metadata?.age_minutes && (
            <p className="empty-state-metadata">
              Última actualización: hace {Math.round(marketData.metadata.age_minutes)} minutos
            </p>
          )}
          <button
            type="button"
            onClick={handleRefresh}
            disabled={isRefetching}
            className="chart-retry-button"
            aria-label="Reintentar carga de datos"
          >
            {isRefetching ? '🔄 Cargando...' : '🔄 Reintentar'}
          </button>
        </div>
      </div>
    )
  }

  // FE-CHART-04: Handle error state with detailed error message
  if (chartState === 'error') {
    const errorMessage = marketError instanceof Error 
      ? marketError.message 
      : typeof marketError === 'object' && marketError !== null
      ? (marketError as any).message || (marketError as any).detail || 'Error desconocido'
      : 'Error al cargar datos de mercado'
    
    return (
      <div className="new-market-chart">
        <div className="error-chart-state">
          <div className="error-state-icon">❌</div>
          <h3>Error al cargar gráfico de mercado</h3>
          <p className="error-message">{errorMessage}</p>
          <div className="error-details">
            <p><strong>Detalles del error:</strong></p>
            <ul className="error-state-reasons">
              <li>No se pudieron cargar las velas del intervalo {interval}</li>
              <li>Verifica que el backend esté funcionando correctamente</li>
              <li>Revisa la consola del navegador para más información</li>
            </ul>
          </div>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={isRefetching}
            className="chart-retry-button"
            aria-label="Reintentar carga de datos"
          >
            {isRefetching ? '🔄 Reintentando...' : '🔄 Reintentar'}
          </button>
        </div>
      </div>
    )
  }

  if (isProcessingError(marketError)) {
    return (
      <div className="new-market-chart">
        <LoadingState message="El pipeline de datos se está ejecutando. Los datos del gráfico estarán disponibles en unos momentos..." />
        <DegradedDataBanner message="El backend está procesando datos. Esta página se actualizará automáticamente cuando los datos estén listos." />
        <button type="button" onClick={handleRefresh} className="chart-refresh-button" style={{ marginTop: '1rem' }}>
          🔄 Reintentar ahora
        </button>
      </div>
    )
  }

  return (
    <div className={`new-market-chart ${shouldDimChart ? 'chart-dimmed' : ''}`}>
      {/* FE-CHART-04: Misalignment banner when as_of is ahead of latest candle */}
      {timestampMisalignment && timestampMisalignment.isAhead && (
        <div className="misalignment-banner" role="alert">
          <span className="misalignment-icon">⚠️</span>
          <div className="misalignment-content">
            <strong>Desalineación de datos detectada</strong>
            <p className="misalignment-details">
              El backend indica que hay datos más recientes ({formatTimestamp(timestampMisalignment.apiLatestTimestamp)}) 
              que la última vela mostrada ({formatTimestamp(timestampMisalignment.latestTimestamp)}). 
              Hay una diferencia de aproximadamente {timestampMisalignment.diffText}.
            </p>
            <p className="misalignment-action">
              Haz clic en "Actualizar" para obtener las velas más recientes.
            </p>
          </div>
        </div>
      )}
      
      {/* FE-CHART-02: Stale data badge/banda */}
      {isStale && (
        <div className="stale-data-banner" role="alert">
          <span className="stale-icon">⚠️</span>
          <div className="stale-content">
            <strong>Datos desactualizados</strong>
            {ageMinutes !== null && ageMinutes !== undefined && (
              <span className="stale-age"> (hace {Math.round(ageMinutes)} minutos)</span>
            )}
            {marketData?.reason && <span className="stale-reason">: {marketData.reason}</span>}
          </div>
        </div>
      )}
      
      {/* FE-CHART-03: Data staleness indicator - always show when chart has data */}
      {candleData.length > 0 && (
        <DataStalenessIndicator
          asOf={isAsOfValid ? apiLatestTimestamp : null}
          ageMinutes={ageMinutes ?? null}
          isStale={isStale || !isAsOfValid}
          status={!isAsOfValid ? 'error' : marketData?.status}
          interval={interval}
        />
      )}

      {/* FE-CHART-02: Chart header with refresh button */}
      <div className="chart-header">
        <div className="chart-title">
          <h3>Gráfico de Mercado ({interval})</h3>
          {latestCandle && (
            <span className="latest-candle-info">
              Última vela: {formatTimestamp(latestCandle.timestamp)}
              {!timestampsMatch && apiLatestTimestamp && (
                <span className="timestamp-mismatch-warning"> ⚠️</span>
              )}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={handleRefresh}
          disabled={isRefetching}
          className={`chart-refresh-button ${timestampMisalignment ? 'chart-refresh-button-highlight' : ''}`}
          aria-label="Actualizar datos del gráfico"
          title={timestampMisalignment ? 'Hay datos más recientes disponibles. Haz clic para actualizar.' : 'Actualizar datos del gráfico'}
        >
          {isRefetching ? '🔄 Actualizando...' : '🔄 Actualizar'}
        </button>
      </div>

      {/* FE-CHART-03: OHLC Candlestick Chart - dimmed if data is invalid or stale */}
      {candleData.length > 0 ? (
        <div className={shouldDimChart ? 'chart-container-dimmed' : ''}>
          <ResponsiveContainer width="100%" height={400}>
          <ComposedChart data={candleData} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
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
                if (name.includes('Volumen')) return [`${value.toLocaleString('es-ES')}`, name]
                return [`${formatCurrency(value)}`, name]
              }}
              labelFormatter={(label: string) => formatTimestamp(label)}
              contentStyle={{ background: '#0f172a', borderRadius: 8, border: '1px solid rgba(255,255,255,0.08)' }}
            />
            <Legend />

            {/* FE-CHART-02: Entry range area */}
            {entryRange && (
              <ReferenceArea
                yAxisId="price"
                y1={Math.min(...entryRange)}
                y2={Math.max(...entryRange)}
                fill="#facc15"
                fillOpacity={0.12}
                strokeOpacity={0}
              />
            )}

            {/* FE-CHART-02: Stop Loss marker */}
            {stopLoss && (
              <ReferenceLine
                yAxisId="price"
                y={stopLoss}
                stroke="#f87171"
                strokeDasharray="6 4"
                strokeWidth={2}
                label={{ value: `SL ${formatCurrency(stopLoss)}`, fill: '#f87171', position: 'right', fontSize: 12 }}
              />
            )}

            {/* FE-CHART-02: Take Profit marker */}
            {takeProfit && (
              <ReferenceLine
                yAxisId="price"
                y={takeProfit}
                stroke="#22c55e"
                strokeDasharray="6 4"
                strokeWidth={2}
                label={{ value: `TP ${formatCurrency(takeProfit)}`, fill: '#22c55e', position: 'right', fontSize: 12 }}
              />
            )}

            {/* FE-CHART-02: Current price marker */}
            <ReferenceLine
              yAxisId="price"
              y={currentPrice}
              stroke="#0ea5e9"
              strokeDasharray="8 5"
              strokeWidth={2.4}
              label={{ value: `Spot ${formatCurrency(currentPrice)}`, fill: '#38bdf8', position: 'right', fontSize: 12 }}
            />

            {/* FE-CHART-02: OHLC visualization - High/Low range */}
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="high"
              stroke="#94a3b8"
              strokeWidth={1}
              dot={false}
              activeDot={false}
              name="Máximo"
              strokeDasharray="2 2"
            />
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="low"
              stroke="#94a3b8"
              strokeWidth={1}
              dot={false}
              activeDot={false}
              name="Mínimo"
              strokeDasharray="2 2"
            />
            
            {/* FE-CHART-02: Close price line (main trend) */}
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="close"
              stroke="#38bdf8"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 5, fill: '#0ea5e9', stroke: '#fff', strokeWidth: 2 }}
              name="Cierre"
            />
            
            {/* FE-CHART-02: Open price line */}
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="open"
              stroke="#64748b"
              strokeWidth={1.5}
              dot={false}
              activeDot={false}
              name="Apertura"
              strokeDasharray="3 3"
            />

            {/* FE-CHART-02: Volume bars */}
            <Bar
              yAxisId="volume"
              dataKey="volume"
              fill="rgba(100, 116, 139, 0.5)"
              barSize={8}
              name="Volumen"
            />
          </ComposedChart>
        </ResponsiveContainer>
        </div>
      ) : (
        <div className="empty-chart-state">
          <p>⚠️ <strong>No hay datos de velas disponibles</strong></p>
          <p>Los datos de mercado fueron cargados pero no contienen velas para renderizar el gráfico.</p>
        </div>
      )}

      {/* FE-CHART-02: Chart footer with metadata */}
      <div className="chart-footer">
        {latestCandle && (
          <p>
            Spot actual: <strong>{formatCurrency(currentPrice)}</strong>
            {' — '}
            {formatTimestamp(latestCandle.timestamp)}
          </p>
        )}
        {/* FE-CHART-03: Show metadata with error state if as_of is invalid */}
        {isAsOfValid && apiLatestTimestamp ? (
          <p className={isStale ? 'data-stale-badge' : 'data-fresh-badge'}>
            <span className="metadata-label">Última vela ({interval}):</span>{' '}
            <strong>{formatTimestamp(apiLatestTimestamp)}</strong>
            {!timestampsMatch && (
              <span className="timestamp-mismatch-warning"> ⚠️ Timestamp no coincide</span>
            )}
          </p>
        ) : !isAsOfValid && candleData.length > 0 ? (
          <p className="data-error-badge">
            <span className="metadata-label">⚠️ Error:</span>{' '}
            <strong>No se pudo determinar la frescura de los datos (as_of inválido o faltante)</strong>
          </p>
        ) : null}
        {candleData.length > 0 && (
          <p className="candle-count">
            Mostrando {candleData.length} {candleData.length === 1 ? 'vela' : 'velas'}
          </p>
        )}
      </div>
    </div>
  )
}

