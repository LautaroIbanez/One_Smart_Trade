import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom/vitest'
import { RealVsTheoretical } from '../RealVsTheoretical'
import * as hooks from '../../../api/hooks'

// Mock the hook
vi.mock('../../../api/hooks', () => ({
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

describe('RealVsTheoretical', () => {
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
      isError: false,
    })

    render(<RealVsTheoretical />, { wrapper: createWrapper() })
    expect(screen.getByText(/Cargando datos de ejecución/i)).toBeInTheDocument()
  })

  it('renders error state when no data', () => {
    ;(hooks.usePerformanceSummary as any).mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
    })

    render(<RealVsTheoretical />, { wrapper: createWrapper() })
    expect(screen.getByText(/Error al cargar datos de ejecución/i)).toBeInTheDocument()
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
        },
        equity_theoretical: [10000, 10100, 10200],
        equity_realistic: [10000, 10080, 10160],
        equity_curve: [
          { timestamp: '2023-01-01', equity_theoretical: 10000, equity_realistic: 10000 },
          { timestamp: '2023-01-02', equity_theoretical: 10100, equity_realistic: 10080 },
        ],
        tracking_error_metrics: {
          rmse: 95.5,
        },
        tracking_error: {
          max_divergence_bps: 180.0,
        },
      },
      equity_theoretical: [10000, 10100, 10200],
      equity_realistic: [10000, 10080, 10160],
      tracking_error_rmse: 95.5,
      tracking_error_max: 180.0,
      has_realistic_data: true,
    }

    ;(hooks.usePerformanceSummary as any).mockReturnValue({
      data: degradedPayload,
      isLoading: false,
      isError: false,
    })

    render(<RealVsTheoretical />, { wrapper: createWrapper() })

    await waitFor(() => {
      // Should show degraded mode banner
      expect(screen.getByText(/⚠️.*Modo degradado/i)).toBeInTheDocument()
      expect(screen.getByText(/Data freshness validation failed/i)).toBeInTheDocument()
    })

    // Should still render the component (not crash)
    expect(screen.getByText(/Ejecución Real vs. Teórica/i)).toBeInTheDocument()
  })

  it('renders placeholder when degraded payload has no equity data', async () => {
    const degradedPayload = {
      status: 'error',
      message: 'Data freshness validation failed',
      fallback_summary: {
        source: 'db_cache',
        metrics: {},
        // No equity data
      },
      tracking_error_rmse: 95.5,
    }

    ;(hooks.usePerformanceSummary as any).mockReturnValue({
      data: degradedPayload,
      isLoading: false,
      isError: false,
    })

    render(<RealVsTheoretical />, { wrapper: createWrapper() })

    await waitFor(() => {
      // Should show degraded mode banner
      expect(screen.getByText(/⚠️.*Modo degradado/i)).toBeInTheDocument()
      // Should show placeholder for missing equity data
      expect(screen.getByText(/Datos de equity no disponibles en modo degradado/i)).toBeInTheDocument()
    })

    // Should not crash
    expect(screen.getByText(/Ejecución Real vs. Teórica/i)).toBeInTheDocument()
  })

  it('handles empty arrays gracefully', async () => {
    const payloadWithEmptyArrays = {
      status: 'success',
      equity_theoretical: [],
      equity_realistic: [],
      equity_curve: [],
      has_realistic_data: false,
    }

    ;(hooks.usePerformanceSummary as any).mockReturnValue({
      data: payloadWithEmptyArrays,
      isLoading: false,
      isError: false,
    })

    render(<RealVsTheoretical />, { wrapper: createWrapper() })

    await waitFor(() => {
      // Should show no realistic data banner
      expect(screen.getByText(/⚠️ Sin datos realistas/i)).toBeInTheDocument()
    })

    // Should not crash
    expect(screen.getByText(/Ejecución Real vs. Teórica/i)).toBeInTheDocument()
  })

  it('renders successfully with valid data', async () => {
    const validPayload = {
      status: 'success',
      equity_theoretical: [10000, 10100, 10200],
      equity_realistic: [10000, 10080, 10160],
      equity_curve: [
        { timestamp: '2023-01-01', equity_theoretical: 10000, equity_realistic: 10000 },
        { timestamp: '2023-01-02', equity_theoretical: 10100, equity_realistic: 10080 },
      ],
      tracking_error_rmse: 95.5,
      tracking_error_max: 180.0,
      has_realistic_data: true,
      orderbook_fallback_events: 3,
    }

    ;(hooks.usePerformanceSummary as any).mockReturnValue({
      data: validPayload,
      isLoading: false,
      isError: false,
    })

    render(<RealVsTheoretical />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText(/Ejecución Real vs. Teórica/i)).toBeInTheDocument()
      expect(screen.getByText(/Tracking Error RMSE/i)).toBeInTheDocument()
    })

    // Should not show degraded banner
    expect(screen.queryByText(/⚠️.*Modo degradado/i)).not.toBeInTheDocument()
  })
})

