import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom/vitest'
import { SignalCompliance } from '../SignalCompliance'
import * as hooks from '../../../api/hooks'

// Mock the hook
vi.mock('../../../api/hooks', () => ({
  useSignalPerformance: vi.fn(),
}))

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('SignalCompliance', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders loading state', () => {
    ;(hooks.useSignalPerformance as any).mockReturnValue({
      data: null,
      isLoading: true,
      isError: false,
    })

    render(<SignalCompliance />, { wrapper: createWrapper() })
    expect(screen.getByText(/Cargando desempeño de señales/i)).toBeInTheDocument()
  })

  it('renders error state when no data', () => {
    ;(hooks.useSignalPerformance as any).mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
    })

    render(<SignalCompliance />, { wrapper: createWrapper() })
    expect(screen.getByText(/Error al cargar datos de seguimiento de señales/i)).toBeInTheDocument()
  })

  it('shows placeholder when timeline is empty', async () => {
    const payloadWithEmptyTimeline = {
      timeline: [],
      equity_theoretical: [],
      equity_realistic: [],
    }

    ;(hooks.useSignalPerformance as any).mockReturnValue({
      data: payloadWithEmptyTimeline,
      isLoading: false,
      isError: false,
    })

    render(<SignalCompliance />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText(/No hay suficiente histórico para evaluar cumplimiento/i)).toBeInTheDocument()
    })

    // Should not crash
    expect(screen.getByText(/Seguimiento de Señales/i)).toBeInTheDocument()
  })

  it('handles empty equity arrays gracefully', async () => {
    const payloadWithEmptyEquity = {
      timeline: [
        {
          date: '2023-01-01',
          signal: 'BUY',
          level_hit: 'TP',
          return_pct: 5.0,
          deviation_pct: 0,
          tracking_error: 0,
          entry_price: 100,
          exit_price: 105,
          take_profit: 105,
          stop_loss: 95,
        },
      ],
      equity_theoretical: [],
      equity_realistic: [],
      equity_curve: [],
      drawdown_curve: [],
      win_rate: 50,
      average_tracking_error: 0,
      trades_evaluated: 1,
      tracking_error_metrics: {},
    }

    ;(hooks.useSignalPerformance as any).mockReturnValue({
      data: payloadWithEmptyEquity,
      isLoading: false,
      isError: false,
    })

    render(<SignalCompliance />, { wrapper: createWrapper() })

    await waitFor(() => {
      // Should show placeholder for missing equity data
      expect(screen.getByText(/Datos de equity no disponibles/i)).toBeInTheDocument()
    })

    // Should still render the table
    expect(screen.getByText(/Seguimiento de Señales/i)).toBeInTheDocument()
    expect(screen.getByText(/Señales emitidas vs resultado real/i)).toBeInTheDocument()
  })

  it('renders successfully with valid data', async () => {
    const validPayload = {
      timeline: [
        {
          date: '2023-01-01',
          signal: 'BUY',
          level_hit: 'TP',
          return_pct: 5.0,
          deviation_pct: 0,
          tracking_error: 0,
          entry_price: 100,
          exit_price: 105,
          take_profit: 105,
          stop_loss: 95,
          holding_days: 5,
        },
      ],
      equity_theoretical: [1.0, 1.05],
      equity_realistic: [1.0, 1.04],
      equity_curve: [1.0, 1.05],
      drawdown_curve: [0, -0.02],
      win_rate: 50,
      average_tracking_error: 0.01,
      trades_evaluated: 1,
      tracking_error_metrics: {
        mean_deviation: 0.01,
        p95_divergence: 0.02,
        max_divergence: 0.03,
        correlation: 0.98,
        max_drawdown_divergence: 0.01,
      },
    }

    ;(hooks.useSignalPerformance as any).mockReturnValue({
      data: validPayload,
      isLoading: false,
      isError: false,
    })

    render(<SignalCompliance />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText(/Seguimiento de Señales/i)).toBeInTheDocument()
      expect(screen.getByText(/Win rate/i)).toBeInTheDocument()
    })

    // Should render chart when equity data is available
    expect(screen.getByText(/Curvas de Equity: Teórico vs Realista/i)).toBeInTheDocument()
  })
})

