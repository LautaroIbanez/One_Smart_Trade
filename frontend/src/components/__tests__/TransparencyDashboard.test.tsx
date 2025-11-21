import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom/vitest'
import { TransparencyDashboard } from '../TransparencyDashboard'

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

// Mock fetch globally
const mockFetch = vi.fn()
global.fetch = mockFetch

describe('TransparencyDashboard', () => {
  beforeEach(() => {
    mockFetch.mockClear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders loading state initially', () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    })

    render(<TransparencyDashboard />, { wrapper: createWrapper() })
    expect(screen.getByText(/Cargando datos de transparencia/i)).toBeInTheDocument()
  })

  it('renders dashboard with success data', async () => {
    const mockData = {
      semaphore: {
        overall_status: 'pass',
        hash_verification: 'pass',
        dataset_verification: 'pass',
        params_verification: 'pass',
        tracking_error_status: 'pass',
        drawdown_divergence_status: 'pass',
        audit_status: 'pass',
        last_verification: new Date().toISOString(),
      },
      current_hashes: {
        code_commit: 'abc123def456',
        dataset_version: 'sha256:dataset123',
        params_digest: 'sha256:params123',
      },
      hash_verifications: [],
      tracking_error_rolling: {
        '7d': null,
        '30d': null,
        '90d': null,
      },
      drawdown_divergence: null,
      audit_status: {
        total_exports: 10,
        recent_exports_24h: 2,
        hash_changes: [],
        last_export: null,
      },
      timestamp: new Date().toISOString(),
      summary_status: 'success',
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockData,
    })

    render(<TransparencyDashboard />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText(/Dashboard de Transparencia/i)).toBeInTheDocument()
    })

    expect(screen.getByText(/Estado General/i)).toBeInTheDocument()
    expect(screen.getByText(/Hashes Vigentes/i)).toBeInTheDocument()
  })

  it('renders dashboard with error status but fallback_summary populated', async () => {
    const mockData = {
      semaphore: {
        overall_status: 'warn',
        hash_verification: 'pass',
        dataset_verification: 'pass',
        params_verification: 'pass',
        tracking_error_status: 'pass',
        drawdown_divergence_status: 'warn',
        audit_status: 'pass',
        last_verification: new Date().toISOString(),
      },
      current_hashes: {
        code_commit: 'abc123def456',
        dataset_version: 'sha256:dataset123',
        params_digest: 'sha256:params123',
      },
      hash_verifications: [
        {
          hash_type: 'code_commit',
          current_hash: 'abc123def456',
          stored_hash: 'abc123def456',
          status: 'pass',
          message: 'Code commit matches',
          timestamp: new Date().toISOString(),
        },
      ],
      tracking_error_rolling: {
        '7d': null,
        '30d': null,
        '90d': null,
      },
      drawdown_divergence: {
        theoretical_max_dd: 0.0,
        realistic_max_dd: 0.0,
        divergence_pct: 0.0,
        timestamp: new Date().toISOString(),
        metadata: {
          is_stale: true,
          reason: 'tracking_error_metrics_missing',
        },
      },
      audit_status: {
        total_exports: 10,
        recent_exports_24h: 2,
        hash_changes: [],
        last_export: null,
      },
      timestamp: new Date().toISOString(),
      summary_status: 'error',
      summary_message: 'Data freshness validation failed',
      summary_metadata: {
        stale_interval: '1h',
        latest_timestamp: new Date().toISOString(),
        threshold_minutes: 60,
        age_minutes: 120,
        fallback_summary_available: true,
        fallback_summary_source: 'db_cache',
        remediation: 'Ejecuta job_ingest_all para regenerar datasets',
      },
      summary_fallback: {
        source: 'db_cache',
        metrics: {
          cagr: 15.5,
          sharpe: 1.2,
          max_drawdown: 12.3,
        },
        period: {
          start: '2023-01-01T00:00:00',
          end: '2024-01-01T00:00:00',
        },
      },
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockData,
    })

    render(<TransparencyDashboard />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText(/Dashboard de Transparencia/i)).toBeInTheDocument()
    })

    // Verify banner is shown
    expect(screen.getByText(/⚠ Datos en modo degradado \(stale\)/i)).toBeInTheDocument()
    expect(screen.getByText(/Data freshness validation failed/i)).toBeInTheDocument()

    // Verify dashboard sections are rendered (not black screen)
    expect(screen.getByText(/Estado General/i)).toBeInTheDocument()
    expect(screen.getByText(/Hashes Vigentes/i)).toBeInTheDocument()
    expect(screen.getByText(/Verificaciones de Hashes/i)).toBeInTheDocument()

    // Verify semaphore is rendered
    expect(screen.getByText(/PASS/i)).toBeInTheDocument()
    expect(screen.getByText(/WARN/i)).toBeInTheDocument()

    // Verify hashes are rendered
    expect(screen.getByText(/Code Commit/i)).toBeInTheDocument()
  })

  it('renders banner with metadata details when summary_status is error', async () => {
    const mockData = {
      semaphore: {
        overall_status: 'warn',
        hash_verification: 'pass',
        dataset_verification: 'pass',
        params_verification: 'pass',
        tracking_error_status: 'pass',
        drawdown_divergence_status: 'warn',
        audit_status: 'pass',
        last_verification: new Date().toISOString(),
      },
      current_hashes: {
        code_commit: 'abc123def456',
        dataset_version: 'sha256:dataset123',
        params_digest: 'sha256:params123',
      },
      hash_verifications: [],
      tracking_error_rolling: {
        '7d': null,
        '30d': null,
        '90d': null,
      },
      drawdown_divergence: null,
      audit_status: {
        total_exports: 0,
        recent_exports_24h: 0,
        hash_changes: [],
        last_export: null,
      },
      timestamp: new Date().toISOString(),
      summary_status: 'error',
      summary_message: 'Data freshness validation failed',
      summary_metadata: {
        stale_interval: '1h',
        latest_timestamp: '2024-01-01T12:00:00Z',
        threshold_minutes: 60,
        age_minutes: 120.5,
        fallback_summary_available: true,
        fallback_summary_source: 'db_cache',
        remediation: 'Ejecuta job_ingest_all para regenerar datasets 1h/1d antes de reintentar.',
      },
      summary_fallback: {
        source: 'db_cache',
        metrics: {},
        period: {
          start: '2023-01-01T00:00:00',
          end: '2024-01-01T00:00:00',
        },
      },
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockData,
    })

    render(<TransparencyDashboard />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText(/⚠ Datos en modo degradado \(stale\)/i)).toBeInTheDocument()
    })

    // Verify banner shows metadata details
    expect(screen.getByText(/Origen:/i)).toBeInTheDocument()
    expect(screen.getByText(/db_cache/i)).toBeInTheDocument()
    expect(screen.getByText(/Período:/i)).toBeInTheDocument()
    expect(screen.getByText(/Intervalo afectado:/i)).toBeInTheDocument()
    expect(screen.getByText(/1h/i)).toBeInTheDocument()
    expect(screen.getByText(/Antigüedad aprox.:/i)).toBeInTheDocument()
    expect(screen.getByText(/120.50 minutos/i)).toBeInTheDocument()
    expect(screen.getByText(/Acción sugerida:/i)).toBeInTheDocument()
  })

  it('does not show black screen when summary_status is error with fallback', async () => {
    const mockData = {
      semaphore: {
        overall_status: 'warn',
        hash_verification: 'pass',
        dataset_verification: 'pass',
        params_verification: 'pass',
        tracking_error_status: 'pass',
        drawdown_divergence_status: 'warn',
        audit_status: 'pass',
        last_verification: new Date().toISOString(),
      },
      current_hashes: {
        code_commit: 'abc123def456',
        dataset_version: 'sha256:dataset123',
        params_digest: 'sha256:params123',
      },
      hash_verifications: [],
      tracking_error_rolling: {
        '7d': null,
        '30d': null,
        '90d': null,
      },
      drawdown_divergence: {
        theoretical_max_dd: 0.0,
        realistic_max_dd: 0.0,
        divergence_pct: 0.0,
        timestamp: new Date().toISOString(),
        metadata: { is_stale: true },
      },
      audit_status: {
        total_exports: 5,
        recent_exports_24h: 1,
        hash_changes: [],
        last_export: null,
      },
      timestamp: new Date().toISOString(),
      summary_status: 'error',
      summary_message: 'Data freshness validation failed',
      summary_metadata: {
        stale_interval: '1h',
        fallback_summary_available: true,
      },
      summary_fallback: {
        source: 'db_cache',
        metrics: {
          cagr: 15.5,
        },
        period: {
          start: '2023-01-01T00:00:00',
          end: '2024-01-01T00:00:00',
        },
      },
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockData,
    })

    render(<TransparencyDashboard />, { wrapper: createWrapper() })

    await waitFor(() => {
      // Verify dashboard is rendered (not black screen)
      expect(screen.getByText(/Dashboard de Transparencia/i)).toBeInTheDocument()
      expect(screen.getByText(/Estado General/i)).toBeInTheDocument()
      expect(screen.getByText(/Hashes Vigentes/i)).toBeInTheDocument()
      expect(screen.getByText(/Estado de Auditorías/i)).toBeInTheDocument()
    })

    // Verify semaphore section is visible
    const semaphoreSection = screen.getByText(/Estado General/i).closest('.semaphore-section')
    expect(semaphoreSection).toBeInTheDocument()

    // Verify hashes section is visible
    const hashesSection = screen.getByText(/Hashes Vigentes/i).closest('.hashes-section')
    expect(hashesSection).toBeInTheDocument()

    // Verify banner is shown
    expect(screen.getByText(/⚠ Datos en modo degradado \(stale\)/i)).toBeInTheDocument()
  })

  it('shows error banner when no fallback is available', async () => {
    const mockData = {
      status: 'error',
      message: 'No data available',
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockData,
    })

    render(<TransparencyDashboard />, { wrapper: createWrapper() })

    await waitFor(() => {
      expect(screen.getByText(/No data available/i)).toBeInTheDocument()
    })

    // Should not show dashboard sections when no data
    expect(screen.queryByText(/Estado General/i)).not.toBeInTheDocument()
  })
})

