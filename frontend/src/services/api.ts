import axios from 'axios'
import { getApiBaseUrl } from '../utils/apiConfig'

const API_BASE_URL = getApiBaseUrl()

// Global request timeout: 25 seconds
// This ensures requests fail fast rather than hanging indefinitely
const REQUEST_TIMEOUT_MS = 25000

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: REQUEST_TIMEOUT_MS,
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
  confidence_raw: number
  confidence_calibrated: number
  confidence_band?: {
    lower: number
    upper: number
    source?: string
    note?: string
  }
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
  calibration_metadata?: Record<string, unknown>
  timestamp: string
  disclaimer: string
}

export interface HistorySparklinePoint {
  timestamp: string
  theoretical: number
  realistic: number
}

export interface HistoryInsights {
  sparkline_series: Record<string, HistorySparklinePoint[]>
  stats: Record<string, number>
}

export interface RecommendationHistoryItem {
  id: number
  timestamp: string
  date: string
  signal: 'BUY' | 'HOLD' | 'SELL'
  status: string
  execution_status: string
  exit_reason: string | null
  entry_price: number | null
  exit_price: number | null
  return_pct: number | null
  theoretical_return_pct: number | null
  realistic_return_pct: number | null
  tracking_error_pct: number | null
  tracking_error_bps: number | null
  divergence_flag: boolean
  code_commit: string | null
  dataset_version: string | null
  ingestion_timestamp: string | null
  seed: number | null
  params_digest: string | null
  config_version: string | null
  snapshot_url: string | null
  risk_metrics: Record<string, unknown> | null
  backtest_run_id: string | null
  backtest_cagr: number | null
  backtest_win_rate: number | null
  backtest_risk_reward_ratio: number | null
  backtest_max_drawdown: number | null
  backtest_slippage_bps: number | null
}

export interface RecommendationHistoryResponse {
  items: RecommendationHistoryItem[]
  next_cursor: string | null
  has_more: boolean
  filters: Record<string, unknown>
  insights: HistoryInsights | null
  download_url: string | null
}

export interface SignalPerformancePoint {
  date: string
  signal: 'BUY' | 'HOLD' | 'SELL'
  entry_price: number
  entry_price_realistic: number | null
  stop_loss: number
  take_profit: number
  exit_price: number
  exit_price_realistic: number | null
  level_hit: string
  holding_days: number
  return_pct: number
  return_pct_realistic: number | null
  tracking_error: number
  deviation_pct: number | null
  entry_slippage_pct: number | null
  exit_slippage_pct: number | null
  hit_date: string | null
  signal_breakdown: Record<string, unknown>
}

export interface SignalPerformanceResponse {
  status: string
  timeline: SignalPerformancePoint[]
  equity_curve: number[]
  equity_theoretical: number[] | null
  equity_realistic: number[] | null
  drawdown_curve: number[]
  win_rate: number
  average_tracking_error: number
  trades_evaluated: number
  tracking_error_metrics: Record<string, unknown>
}

export const getTodayRecommendation = async (): Promise<Recommendation> => {
  const response = await apiClient.get<Recommendation>('/api/v1/recommendation/today')
  return response.data
}

export const getRecommendationHistory = async (limit: number = 10): Promise<RecommendationHistoryResponse> => {
  const response = await apiClient.get<RecommendationHistoryResponse>('/api/v1/recommendation/history', {
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

