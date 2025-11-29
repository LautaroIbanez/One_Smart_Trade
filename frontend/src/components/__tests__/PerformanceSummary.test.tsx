import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom/vitest'
import PerformanceSummary from '../PerformanceSummary'
import * as hooks from '../../api/hooks'

// Mock the hooks
vi.mock('../../api/hooks', () => ({
  usePerformanceSummary: vi.fn(),
  useDataStatus: vi.fn(),
  usePipelineStatus: vi.fn(),
  useCalculatePerformanceSummary: vi.fn(),
  isTimeoutError: vi.fn(() => false),
  isBackendDown: vi.fn(() => false),
  isEmptyDatabase: vi.fn(() => false),
  getErrorMessage: vi.fn((error) => error?.message || 'Unknown error'),
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

  it('does not show warning modal in dev mode with stale data but shows degraded banner for metrics_status', async () => {
    const devModePayload = {
      status: 'degraded',
      metrics_status: 'DEV_FALLBACK',
      trade_count: 10,
      metrics: {
        cagr: 10.0,
        sharpe: 0.5,
        max_drawdown: 5.0,
        win_rate: 50,
        profit_factor: 1.2,
        total_trades: 10,
      },
    }

    // Mock data status with dev mode flags
    ;(hooks.useDataStatus as any).mockReturnValue({
      data: {
        status: 'ok',
        latest_open_time: '2024-11-11T00:00:00Z',
        latest_open_time_date: '2024-11-11',
        age_hours: 720,
        age_days: 30, // Datos antiguos
        has_recent_data: true, // TRUE en modo dev aunque age_days > 2
        dev_mode: true,
        allow_stale_inputs: true,
        freshness_policy: 'dev_allow_stale', // Política de dev
        has_seed_data: true,
      },
    })

    // Mock pipeline status (not running)
    ;(hooks.usePipelineStatus as any).mockReturnValue({
      data: {
        status: 'healthy',
      },
    })

    // Mock calculate performance
    ;(hooks.useCalculatePerformanceSummary as any).mockReturnValue({
      mutateAsync: vi.fn(),
    })

    ;(hooks.usePerformanceSummary as any).mockReturnValue({
      data: devModePayload,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })

    render(<PerformanceSummary />, { wrapper: createWrapper() })

    await waitFor(() => {
      // Should show degraded banner because metrics_status=DEV_FALLBACK
      expect(screen.getByText(/🔧 Modo Desarrollo|⚠️ Modo Degradado/i)).toBeInTheDocument()
    })

    // Should NOT show warning modal (even though age_days=30)
    // The modal should not appear because freshness_policy="dev_allow_stale"
    await waitFor(() => {
      const modal = screen.queryByText(/⚠️ Advertencia/i)
      expect(modal).not.toBeInTheDocument()
    })

    // Should render metrics
    expect(screen.getByText(/CAGR/i)).toBeInTheDocument()
    expect(screen.getByText(/10.00%/i)).toBeInTheDocument()
  })

  it('shows warning modal for NO_TRADES even in dev mode', async () => {
    const noTradesPayload = {
      status: 'degraded',
      metrics_status: 'NO_TRADES',
      trade_count: 0,
      metrics: {
        total_trades: 0,
        win_rate: 0,
        profit_factor: 1.0,
        sharpe: 0.0,
        max_drawdown: 0.0,
        cagr: 0.0,
      },
      no_trade_diagnostics: {
        root_cause: 'enter_signals_zero_size',
        reason: 'Strategy generated signals but position sizer calculated zero size.',
      },
    }

    // Mock data status with dev mode flags
    ;(hooks.useDataStatus as any).mockReturnValue({
      data: {
        status: 'ok',
        latest_open_time: '2024-11-11T00:00:00Z',
        latest_open_time_date: '2024-11-11',
        age_hours: 720,
        age_days: 30,
        has_recent_data: true, // TRUE en modo dev
        dev_mode: true,
        allow_stale_inputs: true,
        freshness_policy: 'dev_allow_stale',
        has_seed_data: true,
      },
    })

    // Mock pipeline status (not running)
    ;(hooks.usePipelineStatus as any).mockReturnValue({
      data: {
        status: 'healthy',
      },
    })

    // Mock calculate performance
    ;(hooks.useCalculatePerformanceSummary as any).mockReturnValue({
      mutateAsync: vi.fn(),
    })

    ;(hooks.usePerformanceSummary as any).mockReturnValue({
      data: noTradesPayload,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })

    render(<PerformanceSummary />, { wrapper: createWrapper() })

    await waitFor(() => {
      // Should show warning modal because metrics_status=NO_TRADES
      // (even though freshness_policy="dev_allow_stale")
      expect(screen.getByText(/⚠️ Advertencia/i)).toBeInTheDocument()
      expect(screen.getByText(/Sin trades simulados/i)).toBeInTheDocument()
    })

    // Should also show degraded banner
    expect(screen.getByText(/⚠️.*Modo degradado|🔧 Modo Desarrollo/i)).toBeInTheDocument()
  })

  it('shows warning modal in production mode with stale data', async () => {
    const staleDataPayload = {
      status: 'degraded',
      metrics: {
        cagr: 10.0,
        sharpe: 0.5,
        max_drawdown: 5.0,
        win_rate: 50,
        profit_factor: 1.2,
        total_trades: 10,
      },
    }

    // Mock data status with production mode (strict policy)
    ;(hooks.useDataStatus as any).mockReturnValue({
      data: {
        status: 'ok',
        latest_open_time: '2024-11-11T00:00:00Z',
        latest_open_time_date: '2024-11-11',
        age_hours: 720,
        age_days: 30, // Datos antiguos
        has_recent_data: false, // FALSE en producción
        dev_mode: false,
        allow_stale_inputs: false,
        freshness_policy: 'strict', // Política estricta
      },
    })

    // Mock pipeline status (not running)
    ;(hooks.usePipelineStatus as any).mockReturnValue({
      data: {
        status: 'healthy',
      },
    })

    // Mock calculate performance
    ;(hooks.useCalculatePerformanceSummary as any).mockReturnValue({
      mutateAsync: vi.fn(),
    })

    ;(hooks.usePerformanceSummary as any).mockReturnValue({
      data: staleDataPayload,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })

    render(<PerformanceSummary />, { wrapper: createWrapper() })

    await waitFor(() => {
      // Should show warning modal because has_recent_data=false and freshness_policy="strict"
      expect(screen.getByText(/⚠️ Advertencia/i)).toBeInTheDocument()
      expect(screen.getByText(/Datos desactualizados/i)).toBeInTheDocument()
    })
  })
})

