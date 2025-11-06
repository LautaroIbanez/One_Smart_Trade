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

export const useInvalidateAll = () => {
  const qc = useQueryClient()
  return async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ['recommendation'] }),
      qc.invalidateQueries({ queryKey: ['market'] }),
    ])
  }
}


