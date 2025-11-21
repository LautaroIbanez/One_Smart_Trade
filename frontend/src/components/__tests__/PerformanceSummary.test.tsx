import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom/vitest'
import PerformanceSummary from '../PerformanceSummary'
import * as hooks from '../../api/hooks'

// Mock the hook
vi.mock('../../api/hooks', () => ({
  usePerformanceSummary: vi.fn(),
}))

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('PerformanceSummary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders loading state', () => {
    ;(hooks.usePerformanceSummary as any).mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    })

    render(<PerformanceSummary />, { wrapper: createWrapper() })
    expect(screen.getByText(/Cargando métricas/i)).toBeInTheDocument()
  })

  it('returns null when error and no fallback', () => {
    ;(hooks.usePerformanceSummary as any).mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error('Failed to fetch'),
    })

    const { container } = render(<PerformanceSummary />, { wrapper: createWrapper() })
    expect(container.firstChild).toBeNull()
  })

  it('renders with degraded payload (status:error with fallback_summary)', async () => {
    const degradedPayload = {
      status: 'error',
      message: 'Data freshness validation failed',
      fallback_summary: {
        source: 'db_cache',
        metrics: {
          cagr: 15.5,
          sharpe: 1.2,
          max_drawdown: 12.3,
          win_rate: 58.5,
          profit_factor: 1.8,
          total_trades: 150,
        },
        period: {
          start: '2023-01-01T00:00:00',
          end: '2024-01-01T00:00:00',
        },
      },
      metrics: {
        cagr: 15.5,
        sharpe: 1.2,
        max_drawdown: 12.3,
        win_rate: 58.5,
        profit_factor: 1.8,
        total_trades: 150,
      },
    }

    ;(hooks.usePerformanceSummary as any).mockReturnValue({
      data: degradedPayload,
      isLoading: false,
      error: null,
    })

    render(<PerformanceSummary />, { wrapper: createWrapper() })

    await waitFor(() => {
      // Should show degraded mode banner
      expect(screen.getByText(/⚠️.*Modo degradado/i)).toBeInTheDocument()
      expect(screen.getByText(/Data freshness validation failed/i)).toBeInTheDocument()
    })

    // Should render metrics from fallback
    expect(screen.getByText(/CAGR/i)).toBeInTheDocument()
    expect(screen.getByText(/15.50%/i)).toBeInTheDocument()
    expect(screen.getByText(/Sharpe/i)).toBeInTheDocument()
    expect(screen.getByText(/1.20/i)).toBeInTheDocument()
  })

  it('shows placeholder when degraded payload has no metrics', async () => {
    const degradedPayloadNoMetrics = {
      status: 'error',
      message: 'Data freshness validation failed',
      fallback_summary: {
        source: 'db_cache',
        metrics: {},
      },
      metrics: {},
    }

    ;(hooks.usePerformanceSummary as any).mockReturnValue({
      data: degradedPayloadNoMetrics,
      isLoading: false,
      error: null,
    })

    render(<PerformanceSummary />, { wrapper: createWrapper() })

    await waitFor(() => {
      // Should show degraded mode banner
      expect(screen.getByText(/⚠️.*Modo degradado/i)).toBeInTheDocument()
      // Should show placeholder for missing metrics
      expect(screen.getByText(/Métricas no disponibles en modo degradado/i)).toBeInTheDocument()
    })

    // Should not crash
    expect(screen.getByText(/Resumen de Performance/i)).toBeInTheDocument()
  })

  it('renders successfully with valid data', async () => {
    const validPayload = {
      status: 'success',
      metrics: {
        cagr: 15.5,
        sharpe: 1.2,
        max_drawdown: 12.3,
        win_rate: 58.5,
        profit_factor: 1.8,
        total_trades: 150,
      },
      report_path: '/path/to/report.md',
    }

    ;(hooks.usePerformanceSummary as any).mockReturnValue({
      data: validPayload,
      isLoading: false,
      error: null,
    })

    render(<PerformanceSummary />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText(/Resumen de Performance/i)).toBeInTheDocument()
      expect(screen.getByText(/CAGR/i)).toBeInTheDocument()
    })

    // Should not show degraded banner
    expect(screen.queryByText(/⚠️.*Modo degradado/i)).not.toBeInTheDocument()
  })
})

