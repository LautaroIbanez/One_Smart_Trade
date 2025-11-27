import { describe, expect, it, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import Dashboard from '../Dashboard'

vi.mock('../../components/RecommendationCard', () => ({ default: () => <div data-testid="recommendation-card" /> }))
vi.mock('../../components/HistoryExplorer', () => ({ default: () => <div data-testid="history-explorer" /> }))
vi.mock('../../components/IndicatorsPanel', () => ({ default: () => <div data-testid="indicators-panel" /> }))
vi.mock('../../components/RiskPanel', () => ({ default: () => <div data-testid="risk-panel" /> }))
vi.mock('../../components/PriceLevelsChart', () => ({ PriceLevelsChart: () => <div data-testid="price-chart" /> }))
vi.mock('../../components/AppLayout', () => ({ default: ({ children }: { children: React.ReactNode }) => <div data-testid="app-layout">{children}</div> }))
vi.mock('../../components/PerformanceSummary', () => ({ default: () => <div data-testid="performance-summary" /> }))
vi.mock('../../features/performance/SignalCompliance', () => ({ default: () => <div data-testid="signal-compliance" /> }))
vi.mock('../../features/performance/MonthlyPerformance', () => ({ default: () => <div data-testid="monthly-performance" /> }))
vi.mock('../../features/performance/RealVsTheoretical', () => ({ RealVsTheoretical: () => <div data-testid="real-vs-theoretical" /> }))
vi.mock('../../components/ObservabilityDashboard', () => ({ default: () => <div data-testid="observability-dashboard" /> }))
vi.mock('../../components/TransparencyDashboard', () => ({ default: () => <div data-testid="transparency-dashboard" /> }))
vi.mock('../../components/LivelihoodDashboard', () => ({ default: () => <div data-testid="livelihood-dashboard" /> }))
vi.mock('../../components/UserRiskPanel', () => ({ default: () => <div data-testid="user-risk-panel" /> }))
vi.mock('../../components/shared/ErrorState', () => ({ ErrorState: ({ title }: { title?: string }) => <div role="alert">{title || 'error'}</div> }))
vi.mock('../../components/shared/LoadingState', () => ({ LoadingState: ({ message }: { message: string }) => <div>{message}</div> }))
vi.mock('../../components/shared/DegradedDataBanner', () => ({ DegradedDataBanner: () => <div data-testid="degraded-banner" /> }))
vi.mock('../../utils/recommendation', () => ({
  isTradableRecommendation: () => false,
  getNonTradableMessage: () => 'Sin señal',
}))
vi.mock('../../api/hooks', () => ({
  useTodayRecommendation: () => ({
    data: null,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
  useMarketData: () => ({
    data: { data: [] },
    isLoading: false,
    error: null,
    refetch: vi.fn(),
  }),
}))

const renderWithClient = async () => {
  const client = new QueryClient()
  await act(async () => {
    render(
      <QueryClientProvider client={client}>
        <Dashboard />
      </QueryClientProvider>
    )
  })
}

describe('Dashboard', () => {
  it('renders without crashing when polling helper is available', async () => {
    await renderWithClient()
    expect(screen.getByRole('heading', { name: /One Smart Trade/i })).toBeInTheDocument()
    expect(screen.getByText(/No hay datos suficientes/i)).toBeInTheDocument()
  })
})

