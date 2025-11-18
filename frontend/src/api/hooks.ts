import { useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const api = axios.create({ baseURL: API_BASE_URL, headers: { 'Content-Type': 'application/json' } })

export type Interval = '15m' | '30m' | '1h' | '4h' | '1d' | '1w'
export const analyticsApi = api

export const useTodayRecommendation = () => {
  return useQuery({
    queryKey: ['recommendation', 'today'],
    queryFn: async () => {
      const { data } = await api.get('/api/v1/recommendation/today')
      return data
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
    queryFn: async () => {
      const { data } = await api.get('/api/v1/recommendation/history', { params: finalParams })
      return data
    },
    staleTime: 60_000,
    keepPreviousData: true,
  })
}

export const useSignalPerformance = (lookaheadDays: number = 5, limit: number = 90) => {
  return useQuery({
    queryKey: ['recommendation', 'performance', lookaheadDays, limit],
    queryFn: async () => {
      const { data } = await api.get('/api/v1/recommendation/performance', {
        params: { lookahead_days: lookaheadDays, limit },
      })
      return data
    },
    staleTime: 300_000,
  })
}

export const useMarketData = (interval: Interval) => {
  return useQuery({
    queryKey: ['market', interval],
    queryFn: async () => {
      const { data } = await api.get(`/api/v1/market/${interval}`)
      return data
    },
    staleTime: 30_000,
  })
}

export const usePerformanceSummary = () => {
  return useQuery({
    queryKey: ['performance', 'summary'],
    queryFn: async () => {
      const { data } = await api.get('/api/v1/performance/summary')
      return data
    },
    staleTime: 300_000, // 5 minutes
  })
}

export const useMonthlyPerformance = (pollingInterval: number | false = 30000) => {
  return useQuery({
    queryKey: ['performance', 'monthly'],
    queryFn: async () => {
      const { data } = await api.get('/api/v1/performance/monthly')
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
    queryFn: async () => {
      if (!monthlyReturns || monthlyReturns.length < 3) return null
      const { data } = await analyticsApi.post('/api/v1/analytics/livelihood', {
        monthly_returns: monthlyReturns,
        expenses_target: expensesTarget,
        trials,
        horizon_months: horizonMonths,
        ruin_threshold: ruinThreshold,
      })
      return data as { survival: any; scenarios: any[] }
    },
    enabled: Array.isArray(monthlyReturns) && monthlyReturns.length >= 3,
    staleTime: 60_000,
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
    queryFn: async () => {
      if (!runId) return null
      const { data } = await analyticsApi.get(`/api/v1/analytics/livelihood/${runId}`, {
        params: { expenses_target: expensesTarget, trials, horizon_months: horizonMonths, ruin_threshold: ruinThreshold },
      })
      return data as { survival: any; scenarios: any[] }
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

