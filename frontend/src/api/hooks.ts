import { useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const api = axios.create({ baseURL: API_BASE_URL, headers: { 'Content-Type': 'application/json' } })

export type Interval = '15m' | '30m' | '1h' | '4h' | '1d' | '1w'

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

export const useRecommendationHistory = (limit: number = 10) => {
  return useQuery({
    queryKey: ['recommendation', 'history', limit],
    queryFn: async () => {
      const { data } = await api.get('/api/v1/recommendation/history', { params: { limit } })
      return data
    },
    staleTime: 60_000,
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

export const useInvalidateAll = () => {
  const qc = useQueryClient()
  return async () => {
    // Invalidate all queries to force refetch
    await Promise.all([
      qc.invalidateQueries({ queryKey: ['recommendation'] }),
      qc.invalidateQueries({ queryKey: ['market'] }),
      qc.invalidateQueries({ queryKey: ['performance'] }),
    ])
  }
}


