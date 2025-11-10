import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

export interface Recommendation {
  signal: 'BUY' | 'HOLD' | 'SELL'
  entry_range: {
    min: number
    max: number
    optimal: number
  }
  stop_loss_take_profit: {
    stop_loss: number
    take_profit: number
    stop_loss_pct: number
    take_profit_pct: number
  }
  confidence: number
  current_price: number
  analysis: string
  indicators: Record<string, unknown>
  risk_metrics: Record<string, unknown>
  factors?: Record<string, unknown>
  signal_breakdown?: {
    vectors?: Record<string, number>
    narrative?: string[]
    aggregate_score?: number
    base_confidence?: number
    agreement?: number
    risk_adjusted_confidence?: number
  }
  timestamp: string
  disclaimer: string
}

export interface RecommendationHistory {
  recommendations: Recommendation[]
  count: number
}

export interface SignalPerformancePoint {
  date: string
  signal: 'BUY' | 'HOLD' | 'SELL'
  entry_price: number
  stop_loss: number
  take_profit: number
  exit_price: number
  level_hit: string
  holding_days: number
  return_pct: number
  tracking_error: number
  hit_date?: string
  signal_breakdown?: {
    narrative?: string[]
    vectors?: Record<string, number>
  }
}

export interface SignalPerformanceResponse {
  status: string
  timeline: SignalPerformancePoint[]
  equity_curve: number[]
  drawdown_curve: number[]
  win_rate: number
  average_tracking_error: number
  trades_evaluated: number
}

export const getTodayRecommendation = async (): Promise<Recommendation> => {
  const response = await apiClient.get<Recommendation>('/api/v1/recommendation/today')
  return response.data
}

export const getRecommendationHistory = async (limit: number = 10): Promise<RecommendationHistory> => {
  const response = await apiClient.get<RecommendationHistory>('/api/v1/recommendation/history', {
    params: { limit },
  })
  return response.data
}

export const getSignalPerformance = async (
  lookahead_days: number = 5,
  limit: number = 90,
): Promise<SignalPerformanceResponse> => {
  const response = await apiClient.get<SignalPerformanceResponse>('/api/v1/recommendation/performance', {
    params: { lookahead_days, limit },
  })
  return response.data
}

