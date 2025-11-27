import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import axios, { AxiosError } from 'axios'
import { getApiBaseUrl } from '../utils/apiConfig'
import { getPollingInterval } from '../utils/polling'
import type { RecommendationHistoryResponse, SignalPerformanceResponse } from '../services/api'

export const API_BASE_URL = getApiBaseUrl()

// Global request timeout: 25 seconds
// This ensures requests fail fast rather than hanging indefinitely
const REQUEST_TIMEOUT_MS = 25000

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: REQUEST_TIMEOUT_MS,
  // Treat HTTP 202 (processing) as an error so we can surface a clear message and retry
  validateStatus: (status) => status >= 200 && status < 300 && status !== 202,
})

// Request interceptor: Add AbortController signal to each request
api.interceptors.request.use((config) => {
  // Create AbortController if not already present
  // React Query will pass signal via config.signal
  if (!config.signal && typeof AbortController !== 'undefined') {
    const controller = new AbortController()
    config.signal = controller.signal
    
    // Store controller for potential manual cancellation
    // @ts-ignore - custom property for internal use
    config._abortController = controller
  }
  
  return config
})

// Response interceptor: Enhance timeout errors with user-friendly messages
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    // Handle 202 Accepted (processing) responses
    if (error.response?.status === 202) {
      const processingError = new Error('La operación está en proceso. Por favor, intenta nuevamente en unos momentos.')
      // @ts-ignore - custom properties for error handling
      processingError.isProcessing = true
      // @ts-ignore
      processingError.originalError = error
      // @ts-ignore
      processingError.code = 'PROCESSING'
      // @ts-ignore
      processingError.detail = error.response?.data
      throw processingError
    }
    
    // Enhance timeout errors with distinct error information
    // Timeouts can indicate: 1) Backend is slow/processing, 2) URL is wrong (requests never reach backend)
    if (error.code === 'ECONNABORTED' || error.message.includes('timeout')) {
      const requestedUrl = error.config?.url || error.request?.responseURL || 'unknown'
      const baseUrl = getApiBaseUrl() || 'Vite proxy (localhost:8000)'
      
      const timeoutError = new Error(
        'La solicitud ha excedido el tiempo de espera (25s). ' +
        'El backend puede estar ejecutando el pipeline inicial o ingiriendo datos. Espera a que termine el pipeline (puede tardar varios minutos) y luego recarga la página. Si el problema persiste, verifica que la URL del backend esté correctamente configurada.'
      )
      // @ts-ignore - custom properties for error handling
      timeoutError.isTimeout = true
      // @ts-ignore
      timeoutError.originalError = error
      // @ts-ignore
      timeoutError.code = 'TIMEOUT'
      // @ts-ignore
      timeoutError.requestedUrl = requestedUrl
      // @ts-ignore
      timeoutError.baseUrl = baseUrl
      throw timeoutError
    }
    
    // Enhance network errors - distinguish between backend down vs URL misconfiguration
    if (error.code === 'ERR_NETWORK' || !error.response) {
      // Check if this might be a URL configuration issue
      const requestedUrl = error.config?.url || error.request?.responseURL || 'unknown'
      const baseUrl = getApiBaseUrl() || 'Vite proxy (localhost:8000)'
      
      const networkError = new Error(
        `No se pudo conectar con el backend en ${baseUrl}. ` +
        `El backend puede estar apagado o la URL puede estar mal configurada.`
      )
      // @ts-ignore
      networkError.isNetworkError = true
      // @ts-ignore
      networkError.isBackendDown = true // Flag to indicate backend is likely down
      // @ts-ignore
      networkError.originalError = error
      // @ts-ignore
      networkError.code = 'NETWORK_ERROR'
      // @ts-ignore
      networkError.requestedUrl = requestedUrl
      // @ts-ignore
      networkError.baseUrl = baseUrl
      throw networkError
    }
    
    // Check for 404/503 which might indicate empty database
    if (error.response?.status === 404 || error.response?.status === 503) {
      const detail = error.response?.data?.detail
      // Check if it's a specific error that suggests empty database (no_data, insufficient_history)
      if (detail && typeof detail === 'object' && (detail.status === 'no_data' || detail.status === 'insufficient_history')) {
        const emptyDbError = new Error('La base de datos está vacía o no hay datos suficientes.')
        // @ts-ignore
        emptyDbError.isEmptyDatabase = true
        // @ts-ignore
        emptyDbError.originalError = error
        // @ts-ignore
        emptyDbError.code = 'EMPTY_DATABASE'
        // @ts-ignore
        emptyDbError.detail = detail
        throw emptyDbError
      }
    }
    
    // Re-throw other errors as-is
    throw error
  }
)

export type Interval = '15m' | '30m' | '1h' | '4h' | '1d' | '1w'

// Export the api instance for use in components
export { api }
export const analyticsApi = api

/**
 * Check if an error is a timeout error
 */
export function isTimeoutError(error: unknown): boolean {
  if (error instanceof Error) {
    // @ts-ignore
    return error.isTimeout === true || error.code === 'TIMEOUT'
  }
  if (axios.isAxiosError(error)) {
    return error.code === 'ECONNABORTED' || error.message.includes('timeout')
  }
  return false
}

/**
 * Check if an error is a network error
 */
export function isNetworkError(error: unknown): boolean {
  if (error instanceof Error) {
    // @ts-ignore
    return error.isNetworkError === true || error.code === 'NETWORK_ERROR'
  }
  if (axios.isAxiosError(error)) {
    return error.code === 'ERR_NETWORK' || !error.response
  }
  return false
}

/**
 * Check if an error indicates the backend is down
 */
export function isBackendDown(error: unknown): boolean {
  if (error instanceof Error) {
    // @ts-ignore
    return error.isBackendDown === true
  }
  if (axios.isAxiosError(error)) {
    return error.code === 'ERR_NETWORK' || !error.response
  }
  return false
}

/**
 * Check if an error indicates empty database
 */
export function isEmptyDatabase(error: unknown): boolean {
  if (error instanceof Error) {
    // @ts-ignore
    return error.isEmptyDatabase === true || error.code === 'EMPTY_DATABASE'
  }
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (detail && typeof detail === 'object') {
      return detail.status === 'no_data' || detail.status === 'insufficient_history'
    }
  }
  return false
}

/**
 * Check if an error indicates the operation is still processing
 */
export function isProcessingError(error: unknown): boolean {
  if (error instanceof Error) {
    // @ts-ignore
    return error.isProcessing === true || error.code === 'PROCESSING'
  }
  if (axios.isAxiosError(error)) {
    return error.response?.status === 202
  }
  return false
}

/**
 * Get user-friendly error message based on error type
 */
export function getErrorMessage(error: unknown): string {
  if (isTimeoutError(error)) {
    return 'La solicitud ha excedido el tiempo de espera (25s). El backend puede estar ejecutando el pipeline inicial o ingiriendo datos. Espera a que termine el pipeline (puede tardar varios minutos) y luego recarga la página.'
  }
  if (isEmptyDatabase(error)) {
    return 'La base de datos está vacía o no hay datos suficientes. Ejecuta el pipeline de ingestión para poblar los datos.'
  }
  if (isBackendDown(error)) {
    return 'El backend no está corriendo o no se puede conectar. Asegúrate de que el servidor esté activo.'
  }
  if (isNetworkError(error)) {
    return 'No se pudo conectar con el backend. Verifica tu conexión a internet e intenta nuevamente.'
  }
  if (axios.isAxiosError(error)) {
    if (error.response?.data?.detail) {
      const detail = error.response.data.detail
      if (typeof detail === 'string') return detail
      if (typeof detail === 'object' && detail.message) return String(detail.message)
    }
    return error.response?.statusText || error.message || 'Ha ocurrido un error desconocido'
  }
  if (error instanceof Error) {
    return error.message
  }
  return 'Ha ocurrido un error desconocido'
}

// Helper function for logging (if not available, use console)
const logger = {
  info: (msg: string, ...args: any[]) => console.log(`[INFO] ${msg}`, ...args),
  warn: (msg: string, ...args: any[]) => console.warn(`[WARN] ${msg}`, ...args),
  error: (msg: string, ...args: any[]) => console.error(`[ERROR] ${msg}`, ...args),
}

// Safe default recommendation structure for degraded/dev mode
const DEFAULT_RECOMMENDATION = {
  signal: 'HOLD' as const,
  entry_range: { min: 0, max: 0, optimal: 0 },
  stop_loss_take_profit: { stop_loss: 0, take_profit: 0, stop_loss_pct: 0, take_profit_pct: 0 },
  current_price: 0,
  confidence: 0,
  confidence_raw: 0,
  confidence_calibrated: 0,
  analysis: 'No hay datos disponibles. La recomendación se está generando o los datos están en modo degradado.',
  indicators: {},
  risk_metrics: { dev_fallback: true, degraded_mode: true },
  timestamp: new Date().toISOString(),
  disclaimer: 'Datos en modo degradado. Esta recomendación puede no reflejar las condiciones actuales del mercado.',
  status: 'degraded' as const,
  dev_fallback: true,
}

export const useTodayRecommendation = () => {
  return useQuery({
    queryKey: ['recommendation', 'today'],
    queryFn: async ({ signal }) => {
      const maxRetries = 3
      let lastError: any = null
      
      for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
          // Pass signal to Axios for automatic cancellation
          const { data } = await api.get('/api/v1/recommendation/today', { signal })
          // Ensure we always return a structured object, never null/undefined
          return data || DEFAULT_RECOMMENDATION
        } catch (error: any) {
          lastError = error
          
          // Handle 202 Accepted (processing) - retry with exponential backoff
          if (error?.response?.status === 202 || isProcessingError(error)) {
            if (attempt < maxRetries) {
              const retryDelay = Math.min(1000 * Math.pow(2, attempt), 10000) // Max 10s
              logger.info(`Recommendation processing (202), retrying in ${retryDelay}ms (attempt ${attempt + 1}/${maxRetries})`)
              await new Promise(resolve => setTimeout(resolve, retryDelay))
              continue
            } else {
              // After max retries, return processing state
              return {
                ...DEFAULT_RECOMMENDATION,
                status: 'processing',
                message: 'La recomendación se está generando. Por favor, espera unos momentos e intenta nuevamente.',
                processing: true,
              }
            }
          }
          
          // Handle HTTP 503/400 with guardrail states
          // These are VALID guardrail states, not errors - return them as data so UI can display them informatively
          // Guardrails protect signal quality by blocking generation when data is stale, incomplete, or insufficient
          if ((error?.response?.status === 503 || error?.response?.status === 400) && error?.response?.data?.detail) {
            const detail = error.response.data.detail
            // If detail is an object with a guardrail status, return it as data (not error)
            if (typeof detail === 'object' && detail.status) {
              const guardrailStatuses = [
                'data_stale',
                'data_gaps', 
                'insufficient_history',
                'capital_missing',
                'daily_risk_limit_exceeded',
              ]
              if (guardrailStatuses.includes(detail.status)) {
                // Return guardrail state as valid data - these are not errors, they're informative states
                // The UI will display these with appropriate instructions, not as red error screens
                return detail
              }
            }
          }
          
          // For timeout errors, retry with exponential backoff (only in dev/startup scenarios)
          if (isTimeoutError(error) && attempt < maxRetries) {
            const retryDelay = Math.min(2000 * Math.pow(2, attempt), 15000) // Max 15s for timeouts
            logger.info(`Request timeout, retrying in ${retryDelay}ms (attempt ${attempt + 1}/${maxRetries})`)
            await new Promise(resolve => setTimeout(resolve, retryDelay))
            continue
          }
          
          // For 200 responses with empty/null body, return default structure
          if (error?.response?.status === 200 && (!error.response.data || error.response.data === null)) {
            return DEFAULT_RECOMMENDATION
          }
          
          // If this is the last attempt or non-retryable error, throw
          if (attempt === maxRetries || (!isTimeoutError(error) && !isProcessingError(error))) {
            throw error
          }
        }
      }
      
      // Should never reach here, but TypeScript needs this
      throw lastError
    },
    staleTime: 60_000,
    // Provide placeholder data to prevent loading spinner lock
    placeholderData: (previousData) => previousData || DEFAULT_RECOMMENDATION,
    retry: false, // We handle retries manually above
    refetchInterval: (query) => {
      const data = query.state.data as any
      const status = data?.status
      const isStale = query.isStale()
      const cacheAge = query.state.dataUpdatedAt ? Date.now() - query.state.dataUpdatedAt : undefined
      
      // Only poll if status is processing/degraded, otherwise use slow polling
      return getPollingInterval(status, isStale, cacheAge)
    },
  })
}

export const useGenerateRecommendation = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      // Problem 1: Increase timeout for generation endpoint (can take > 25s)
      // Create a separate axios instance with longer timeout for this operation
      const { data } = await axios.post(
        `${API_BASE_URL}/api/v1/recommendation/generate`,
        {},
        {
          headers: { 'Content-Type': 'application/json' },
          timeout: 120_000, // 120 seconds for heavy computation (backtest + guardrails)
        }
      )
      return data
    },
    onSuccess: () => {
      // Invalidate and refetch recommendation query after successful generation
      queryClient.invalidateQueries({ queryKey: ['recommendation', 'today'] })
    },
  })
}

export interface RecommendationHistoryParams {
  limit?: number
  cursor?: string | null
  start_date?: string | null
  end_date?: string | null
  signal?: 'BUY' | 'SELL' | 'HOLD' | ''
  result?: string | null
  status?: string | null
  tracking_error_min?: number | null
  tracking_error_max?: number | null
}

const sanitizeHistoryParams = (params?: RecommendationHistoryParams) => {
  const payload: Record<string, unknown> = {}
  const source = { limit: 25, ...(params || {}) }
  Object.entries(source).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    payload[key] = value
  })
  return payload
}

export const useRecommendationHistory = (params?: RecommendationHistoryParams) => {
  const finalParams = sanitizeHistoryParams(params)
  return useQuery<RecommendationHistoryResponse>({
    queryKey: ['recommendation', 'history', finalParams],
    queryFn: async ({ signal }) => {
      const { data } = await api.get<RecommendationHistoryResponse>('/api/v1/recommendation/history', { 
        params: finalParams,
        signal,
      })
      return data
    },
    staleTime: 60_000,
    placeholderData: (previousData) => previousData,
  })
}

export const useSignalPerformance = (lookaheadDays: number = 5, limit: number = 90) => {
  return useQuery<SignalPerformanceResponse>({
    queryKey: ['recommendation', 'performance', lookaheadDays, limit],
    queryFn: async ({ signal }) => {
      const { data } = await api.get<SignalPerformanceResponse>('/api/v1/recommendation/performance', {
        params: { lookahead_days: lookaheadDays, limit },
        signal,
      })
      return data
    },
    staleTime: 300_000,
  })
}

export const useMarketData = (interval: Interval) => {
  return useQuery({
    queryKey: ['market', interval],
    queryFn: async ({ signal }) => {
      const { data } = await api.get(`/api/v1/market/${interval}`, { signal })
      return data
    },
    staleTime: 300_000, // 5 minutes - increased from 30s
    refetchInterval: (query) => {
      const data = query.state.data as any
      const status = data?.status
      const isStale = query.isStale()
      const cacheAge = query.state.dataUpdatedAt ? Date.now() - query.state.dataUpdatedAt : undefined
      
      return getPollingInterval(status, isStale, cacheAge)
    },
  })
}

// Safe default performance structure for degraded/dev mode
const DEFAULT_PERFORMANCE = {
  status: 'degraded' as const,
  metrics: {
    total_trades: 0,
    winning_trades: 0,
    losing_trades: 0,
    win_rate: 0,
    profit_factor: 1.0,
    sharpe_ratio: 0.0,
    calmar_ratio: 0.0,
    max_drawdown: 0.0,
    cagr: 0.0,
    expectancy_r: 0.0,
    avg_rr: 1.0,
  },
  equity_curve: [] as Array<{ timestamp: string; value: number }>,
  equity_theoretical: [] as Array<{ timestamp: string; value: number }>,
  equity_realistic: [] as Array<{ timestamp: string; value: number }>,
  degraded_mode: true,
  dev_fallback: true,
  message: 'Datos en modo degradado. Las métricas se están calculando en segundo plano.',
}

export const usePerformanceSummary = (enabled: boolean = true, warmup: boolean = false) => {
  return useQuery({
    queryKey: ['performance', 'summary', warmup],
    queryFn: async ({ signal }) => {
      const maxRetries = 2 // Fewer retries for performance (less critical)
      let lastError: any = null
      
      for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
          const { data } = await api.get('/api/v1/performance/summary', {
            params: { allow_stale_inputs: true, warmup },
            signal,
          })
          // Ensure we always return a structured object, never null/undefined
          // If status is error but arrays/metrics are present, preserve them for degraded rendering
          if (!data || data === null) {
            return DEFAULT_PERFORMANCE
          }
          // If status is error but we have partial metrics, merge with defaults
          if (data.status === 'error' && (!data.metrics || Object.keys(data.metrics).length === 0)) {
            return { ...DEFAULT_PERFORMANCE, ...data, metrics: DEFAULT_PERFORMANCE.metrics }
          }
          return data
        } catch (error: any) {
          lastError = error
          
          // Retry on timeout or processing errors
          if ((isTimeoutError(error) || isProcessingError(error)) && attempt < maxRetries) {
            const retryDelay = Math.min(2000 * Math.pow(2, attempt), 10000)
            logger.info(`Performance summary timeout/processing, retrying in ${retryDelay}ms (attempt ${attempt + 1}/${maxRetries})`)
            await new Promise(resolve => setTimeout(resolve, retryDelay))
            continue
          }
          
          // For 200 responses with empty/null body, return default structure
          if (error?.response?.status === 200 && (!error.response.data || error.response.data === null)) {
            return DEFAULT_PERFORMANCE
          }
          
          // If this is the last attempt or non-retryable error, throw
          if (attempt === maxRetries || (!isTimeoutError(error) && !isProcessingError(error))) {
            throw error
          }
        }
      }
      
      throw lastError
    },
    staleTime: 300_000, // 5 minutes
    enabled, // Allow disabling to prevent automatic fetching
    // Provide placeholder data to prevent loading spinner lock
    placeholderData: (previousData) => previousData || DEFAULT_PERFORMANCE,
    retry: false, // We handle retries manually above
    refetchInterval: (query) => {
      const data = query.state.data as any
      const status = data?.status
      const isStale = query.isStale()
      const cacheAge = query.state.dataUpdatedAt ? Date.now() - query.state.dataUpdatedAt : undefined
      
      // Use centralized polling logic
      return getPollingInterval(status, isStale, cacheAge)
    },
  })
}

export const useCalculatePerformanceSummary = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (allow_stale_inputs: boolean = false) => {
      const { data } = await api.post('/api/v1/performance/summary/calculate', null, {
        params: { allow_stale_inputs },
      })
      return data
    },
    onSuccess: () => {
      // Invalidate and refetch performance summary after successful calculation
      queryClient.invalidateQueries({ queryKey: ['performance', 'summary'] })
    },
  })
}

export interface DataStatusResponse {
  status: string
  latest_open_time: string | null
  latest_open_time_date: string | null
  age_hours: number | null
  age_days: number | null
  has_recent_data: boolean
  interval?: string
  venue?: string
  symbol?: string
  message?: string
}

export const useDataStatus = (
  interval: string = '1d',
  symbol: string = 'BTCUSDT',
  venue: string = 'binance',
  enabled: boolean = true
) => {
  return useQuery({
    queryKey: ['data-status', interval, symbol, venue],
    queryFn: async ({ signal }) => {
      const { data } = await api.get<DataStatusResponse>('/api/v1/operational/data-status', {
        params: { interval, symbol, venue },
        signal,
      })
      return data
    },
    staleTime: 60_000, // 1 minute
    enabled,
    refetchInterval: 300_000, // Refetch every 5 minutes
  })
}

export const useMonthlyPerformance = (pollingInterval: number | false = 30000) => {
  return useQuery({
    queryKey: ['performance', 'monthly'],
    queryFn: async ({ signal }) => {
      const { data } = await api.get('/api/v1/performance/monthly', { signal })
      return data
    },
    staleTime: 300_000, // 5 minutes - increased from 10s
    refetchInterval: (query) => {
      // If explicit polling interval is provided, use it
      if (typeof pollingInterval === 'number') {
        return pollingInterval
      }
      if (pollingInterval === false) {
        return false
      }
      
      // Otherwise use status-based polling
      const data = query.state.data as any
      const status = data?.status
      const isStale = query.isStale()
      const cacheAge = query.state.dataUpdatedAt ? Date.now() - query.state.dataUpdatedAt : undefined
      
      return getPollingInterval(status, isStale, cacheAge)
    },
  })
}

export const useInvalidateAll = () => {
  const qc = useQueryClient()
  return async () => {
    // Invalidate all queries to force refetch
    await Promise.all([
      qc.invalidateQueries({ queryKey: ['recommendation'] }),
      qc.invalidateQueries({ queryKey: ['market'] }),
      qc.invalidateQueries({ queryKey: ['performance'] }),
      qc.invalidateQueries({ queryKey: ['analytics'] }),
    ])
  }
}


export const useLivelihoodFromSeries = (
  monthlyReturns: number[] | undefined,
  expensesTarget: number = 0,
  trials: number = 10000,
  horizonMonths: number = 36,
  ruinThreshold: number = 0.7,
  enabled: boolean = true
) => {
  return useQuery({
    queryKey: ['analytics', 'livelihood', 'series', expensesTarget, trials, horizonMonths, ruinThreshold, monthlyReturns?.length || 0],
    queryFn: async ({ signal }) => {
      if (!monthlyReturns || monthlyReturns.length < 3) return null
      const { data } = await analyticsApi.post('/api/v1/analytics/livelihood', {
        monthly_returns: monthlyReturns,
        expenses_target: expensesTarget,
        trials,
        horizon_months: horizonMonths,
        ruin_threshold: ruinThreshold,
      }, { signal })
      return data as { survival: any; scenarios: any[] }
    },
    enabled: enabled && Array.isArray(monthlyReturns) && monthlyReturns.length >= 3,
    staleTime: 300_000, // 5 minutes (increased from 60s since results are cached on backend)
  })
}

export const useLatestRunId = () => {
  return useQuery({
    queryKey: ['analytics', 'livelihood', 'latest-run-id'],
    queryFn: async ({ signal }) => {
      const { data } = await analyticsApi.get('/api/v1/analytics/livelihood/latest-run-id', { signal })
      return data as { run_id: string | null; source: string | null }
    },
    staleTime: 300_000, // 5 minutes
  })
}

export const useLivelihoodFromRun = (
  runId: string | undefined,
  expensesTarget: number = 0,
  trials: number = 10000,
  horizonMonths: number = 36,
  ruinThreshold: number = 0.7
) => {
  return useQuery({
    queryKey: ['analytics', 'livelihood', 'run', runId, expensesTarget, trials, horizonMonths, ruinThreshold],
    queryFn: async ({ signal }) => {
      if (!runId) return null
      const { data } = await analyticsApi.get(`/api/v1/analytics/livelihood/${runId}`, {
        params: { expenses_target: expensesTarget, trials, horizon_months: horizonMonths, ruin_threshold: ruinThreshold },
        signal,
      })
      return data as { survival: any; scenarios: any[]; periodic_metrics?: any; income_curves?: any }
    },
    enabled: typeof runId === 'string' && runId.length > 0,
    staleTime: 60_000,
  })
}

export const submitLivelihoodFeedback = async (feedback: {
  user_id?: string
  run_id?: string
  rating: number
  comments?: string
  context?: Record<string, unknown>
}) => {
  const { data } = await analyticsApi.post('/api/v1/analytics/feedback', feedback)
  return data as { path: string; md5: string; sha256: string; size: number }
}

