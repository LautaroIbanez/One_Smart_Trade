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
  indicators: Record<string, any>
  risk_metrics: Record<string, any>
  timestamp: string
  disclaimer: string
}

export interface RecommendationHistory {
  recommendations: Recommendation[]
  count: number
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

