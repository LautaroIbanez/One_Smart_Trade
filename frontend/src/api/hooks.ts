import { useQuery, useQueryClient } from '@tanstack/react-query'
import axios, { AxiosError, AxiosRequestConfig } from 'axios'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

// Global request timeout: 25 seconds
// This ensures requests fail fast rather than hanging indefinitely
const REQUEST_TIMEOUT_MS = 25000

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: REQUEST_TIMEOUT_MS,
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
    // Enhance timeout errors with distinct error information
    if (error.code === 'ECONNABORTED' || error.message.includes('timeout')) {
      const timeoutError = new Error('La solicitud ha excedido el tiempo de espera. El backend está ocupado procesando la solicitud.')
      // @ts-ignore - custom properties for error handling
      timeoutError.isTimeout = true
      // @ts-ignore
      timeoutError.originalError = error
      // @ts-ignore
      timeoutError.code = 'TIMEOUT'
      throw timeoutError
    }
    
    // Enhance network errors
    if (error.code === 'ERR_NETWORK' || !error.response) {
      const networkError = new Error('No se pudo conectar con el backend. Verifica tu conexión a internet.')
      // @ts-ignore
      networkError.isNetworkError = true
      // @ts-ignore
      networkError.originalError = error
      // @ts-ignore
      networkError.code = 'NETWORK_ERROR'
      throw networkError
    }
    
    // Re-throw other errors as-is
    throw error
  }
)

export type Interval = '15m' | '30m' | '1h' | '4h' | '1d' | '1w'
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
 * Get user-friendly error message based on error type
 */
export function getErrorMessage(error: unknown): string {
  if (isTimeoutError(error)) {
    return 'La solicitud ha excedido el tiempo de espera. El backend está ocupado procesando la solicitud. Por favor, intenta nuevamente en unos momentos.'
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

export const useTodayRecommendation = () => {
  return useQuery({
    queryKey: ['recommendation', 'today'],
    queryFn: async ({ signal }) => {
      try {
        // Pass signal to Axios for automatic cancellation
        const { data } = await api.get('/api/v1/recommendation/today', { signal })
        return data
      } catch (error: any) {
        // Handle HTTP 400 with capital_missing or daily_risk_limit_exceeded status
        if (error?.response?.status === 400 && error?.response?.data?.detail) {
          const detail = error.response.data.detail
          // If detail is an object with status capital_missing or daily_risk_limit_exceeded, return it as data
          if (typeof detail === 'object' && (detail.status === 'capital_missing' || detail.status === 'daily_risk_limit_exceeded')) {
            return detail
          }
        }
        // Re-throw other errors (including timeout errors)
        throw error
      }
    },
    staleTime: 60_000,
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
  return useQuery({
    queryKey: ['recommendation', 'history', finalParams],
    queryFn: async ({ signal }) => {
      const { data } = await api.get('/api/v1/recommendation/history', { 
        params: finalParams,
        signal,
      })
      return data
    },
    staleTime: 60_000,
    keepPreviousData: true,
  })
}

export const useSignalPerformance = (lookaheadDays: number = 5, limit: number = 90) => {
  return useQuery({
    queryKey: ['recommendation', 'performance', lookaheadDays, limit],
    queryFn: async ({ signal }) => {
      const { data } = await api.get('/api/v1/recommendation/performance', {
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
    staleTime: 30_000,
  })
}

export const usePerformanceSummary = () => {
  return useQuery({
    queryKey: ['performance', 'summary'],
    queryFn: async ({ signal }) => {
      const { data } = await api.get('/api/v1/performance/summary', {
        params: { allow_stale_inputs: true },
        signal,
      })
      return data
    },
    staleTime: 300_000, // 5 minutes
  })
}

export const useMonthlyPerformance = (pollingInterval: number | false = 30000) => {
  return useQuery({
    queryKey: ['performance', 'monthly'],
    queryFn: async ({ signal }) => {
      const { data } = await api.get('/api/v1/performance/monthly', { signal })
      return data
    },
    refetchInterval: pollingInterval,
    staleTime: 10000,
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
  ruinThreshold: number = 0.7
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
    enabled: Array.isArray(monthlyReturns) && monthlyReturns.length >= 3,
    staleTime: 60_000,
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

