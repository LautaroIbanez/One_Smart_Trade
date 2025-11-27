import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, AreaChart, Area } from 'recharts'
import { api } from '../api/hooks'
import { getPollingInterval } from '../utils/polling'
import './TransparencyDashboard.css'

interface HashVerification {
  hash_type: string
  current_hash: string
  stored_hash: string | null
  status: 'pass' | 'warn' | 'fail' | 'unknown'
  message: string
  timestamp: string
}

interface TrackingErrorRolling {
  period_days: number
  mean_deviation: number
  max_divergence: number
  correlation: number
  rmse: number
  annualized_tracking_error: number
  timestamp: string
}

interface DrawdownDivergence {
  theoretical_max_dd: number
  realistic_max_dd: number
  divergence_pct: number
  timestamp: string
}

interface FallbackSummary {
  source?: string
  metrics?: Record<string, any> | null
  period?: { start?: string; end?: string } | null
  report_path?: string | null
  [key: string]: any
}

interface TransparencyDashboardData {
  semaphore: {
    overall_status: 'pass' | 'warn' | 'fail' | 'unknown'
    hash_verification: 'pass' | 'warn' | 'fail' | 'unknown'
    dataset_verification: 'pass' | 'warn' | 'fail' | 'unknown'
    params_verification: 'pass' | 'warn' | 'fail' | 'unknown'
    tracking_error_status: 'pass' | 'warn' | 'fail' | 'unknown'
    drawdown_divergence_status: 'pass' | 'warn' | 'fail' | 'unknown'
    audit_status: 'pass' | 'warn' | 'fail' | 'unknown'
    last_verification: string
  }
  current_hashes: {
    code_commit: string
    dataset_version: string
    params_digest: string
  }
  hash_verifications: HashVerification[]
  tracking_error_rolling: {
    '7d': TrackingErrorRolling | null
    '30d': TrackingErrorRolling | null
    '90d': TrackingErrorRolling | null
  }
  drawdown_divergence: DrawdownDivergence | null
  audit_status: {
    total_exports: number
    recent_exports_24h: number
    hash_changes: Array<{
      type: string
      old: string
      new: string
      timestamp: string
    }>
    last_export: string | null
  }
  timestamp: string
  summary_status?: string
  summary_message?: string
  summary_metadata?: Record<string, any> | null
  summary_details?: unknown
  summary_metrics?: Record<string, any> | null
  summary_period?: { start?: string; end?: string } | null
  summary_fallback?: FallbackSummary | null
}

type DashboardApiResponse = Partial<TransparencyDashboardData> & {
  status?: string
  message?: string
  summary_message?: string
  metadata?: Record<string, any>
  details?: unknown
  summary_status?: string
  summary_metadata?: Record<string, any>
  summary_details?: unknown
  summary_metrics?: Record<string, any> | null
  summary_period?: { start?: string; end?: string } | null
  summary_fallback?: FallbackSummary | null
}

interface DashboardStatusAlert {
  message: string
  details?: string
  lastAttempt?: string
  retryAfterSeconds?: number
  cacheExpiresAt?: string
}

function buildStatusAlert(payload: DashboardApiResponse): DashboardStatusAlert {
  const metadata = payload.metadata || {}
  const rawDetails = (() => {
    if (metadata.summary_message) return metadata.summary_message as string
    if (metadata.remediation) return metadata.remediation as string
    if (typeof payload.details === 'string') return payload.details
    if (payload.details && typeof payload.details === 'object' && 'message' in payload.details) {
      return String((payload.details as { message?: string }).message || '')
    }
    return undefined
  })()

  return {
    message:
      (metadata.user_message as string) ||
      (metadata.summary_message as string) ||
      payload.summary_message ||
      payload.message ||
      'El dashboard de transparencia no está disponible temporalmente.',
    details: rawDetails,
    lastAttempt: (metadata.last_attempt as string) || (metadata.lastAttempt as string),
    retryAfterSeconds:
      (metadata.retry_after_seconds as number | undefined) ??
      (metadata.retryAfterSeconds as number | undefined),
    cacheExpiresAt:
      (metadata.cache_expires_at as string) ||
      (metadata.cacheExpiresAt as string),
  }
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'pass':
      return '#4caf50'
    case 'warn':
      return '#ff9800'
    case 'fail':
      return '#f44336'
    default:
      return '#9e9e9e'
  }
}

function getStatusIcon(status: string): string {
  switch (status) {
    case 'pass':
      return '✓'
    case 'warn':
      return '⚠'
    case 'fail':
      return '✗'
    default:
      return '?'
  }
}

export function TransparencyDashboard() {
  const [autoRefresh, setAutoRefresh] = useState(true)
  
  // Use React Query for shared cache and centralized polling
  const { data: result, isLoading, error, refetch } = useQuery<DashboardApiResponse>({
    queryKey: ['transparency', 'dashboard'],
    queryFn: async ({ signal }) => {
      const { data } = await api.get<DashboardApiResponse>('/api/v1/transparency/dashboard', { signal })
      return data
    },
    staleTime: 300_000, // 5 minutes
    enabled: autoRefresh,
    refetchInterval: (query) => {
      if (!autoRefresh) {
        return false
      }
      
      const data = query.state.data as DashboardApiResponse | undefined
      const status = data?.status || data?.summary_status
      const isStale = query.isStale()
      const cacheAge = query.state.dataUpdatedAt ? Date.now() - query.state.dataUpdatedAt : undefined
      
      return getPollingInterval(status, isStale, cacheAge)
    },
  })

  // Process response data similar to original logic
  const missingMetrics = !result?.semaphore
  const fallbackSummary: FallbackSummary | null =
    result?.summary_fallback && typeof result.summary_fallback === 'object'
      ? (result.summary_fallback as FallbackSummary)
      : null
  const hasFallbackMetrics =
    Boolean(fallbackSummary?.metrics && Object.keys(fallbackSummary.metrics || {}).length > 0) ||
    Boolean(fallbackSummary?.period)
  const summaryErrorPayload: DashboardApiResponse | null =
    result?.summary_status === 'error'
      ? {
          status: result.summary_status,
          message: result.summary_message,
          summary_message: result.summary_message,
          metadata: result.summary_metadata ?? undefined,
          details: result.summary_details ?? undefined,
        }
      : null
  const isErrorPayload = result?.status === 'error'

  // If summary_status is error but we have fallback_summary, use it to populate minimal data
  const shouldUseFallback = result?.summary_status === 'error' && Boolean(fallbackSummary)
  
  // Only show alert if we don't have fallback data to work with
  const alertPayload =
    summaryErrorPayload && hasFallbackMetrics
      ? null
      : summaryErrorPayload ?? (isErrorPayload || (missingMetrics && !shouldUseFallback) ? result : null)

  const statusAlert = alertPayload ? buildStatusAlert(alertPayload) : null
  const data: TransparencyDashboardData | null = 
    (result?.semaphore || shouldUseFallback) ? (result as TransparencyDashboardData) : null
  
  const loading = isLoading
  const fetchData = () => refetch()

  if (loading && !data) {
    return (
      <section className="transparency-dashboard" aria-busy="true">
        <header>
          <h2>Dashboard de Transparencia</h2>
        </header>
        <p>Cargando datos de transparencia...</p>
      </section>
    )
  }

  if (!data) {
    return (
      <section className="transparency-dashboard" aria-live="polite">
        <header>
          <div className="transparency-header-row">
            <h2>Dashboard de Transparencia</h2>
            <div className="transparency-actions">
              <label className="refresh-toggle">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                />
                <span>Actualización automática</span>
              </label>
              <button type="button" className="refresh-button" onClick={fetchData}>
                🔄 Actualizar
              </button>
            </div>
          </div>
        </header>
        <ErrorBanner statusAlert={statusAlert} onRetry={() => refetch()} />
      </section>
    )
  }

  const {
    semaphore,
    current_hashes,
    hash_verifications,
    tracking_error_rolling,
    drawdown_divergence,
    audit_status,
    summary_status,
    summary_message,
    summary_metadata,
    summary_fallback,
  } = data
  const showingFallbackData = summary_status === 'error' && Boolean(summary_fallback)

  return (
    <section className="transparency-dashboard">
      <header>
        <div className="transparency-header-row">
          <h2>Dashboard de Transparencia</h2>
          <div className="transparency-actions">
            <label className="refresh-toggle">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              <span>Actualización automática</span>
            </label>
            <button type="button" className="refresh-button" onClick={() => refetch()}>
              🔄 Actualizar
            </button>
          </div>
        </div>
      </header>

      {statusAlert && <ErrorBanner statusAlert={statusAlert} onRetry={() => refetch()} />}
      {(showingFallbackData || (summary_status === 'error' && summary_fallback)) && (
        <FallbackDataBanner
          message={summary_message}
          metadata={summary_metadata}
          fallbackSummary={summary_fallback}
        />
      )}

      {/* Semaphore Status */}
      <div className="semaphore-section">
        <h3>Estado General</h3>
        <div className="semaphore-grid">
          <div className="semaphore-card" style={{ borderColor: getStatusColor(semaphore.overall_status) }}>
            <div className="semaphore-status" style={{ color: getStatusColor(semaphore.overall_status) }}>
              <span className="semaphore-icon">{getStatusIcon(semaphore.overall_status)}</span>
              <span className="semaphore-label">Estado General</span>
            </div>
            <div className="semaphore-value">{semaphore.overall_status.toUpperCase()}</div>
          </div>
          <div className="semaphore-card" style={{ borderColor: getStatusColor(semaphore.hash_verification) }}>
            <div className="semaphore-status" style={{ color: getStatusColor(semaphore.hash_verification) }}>
              <span className="semaphore-icon">{getStatusIcon(semaphore.hash_verification)}</span>
              <span className="semaphore-label">Hashes</span>
            </div>
          </div>
          <div className="semaphore-card" style={{ borderColor: getStatusColor(semaphore.tracking_error_status) }}>
            <div className="semaphore-status" style={{ color: getStatusColor(semaphore.tracking_error_status) }}>
              <span className="semaphore-icon">{getStatusIcon(semaphore.tracking_error_status)}</span>
              <span className="semaphore-label">Tracking Error</span>
            </div>
          </div>
          <div className="semaphore-card" style={{ borderColor: getStatusColor(semaphore.drawdown_divergence_status) }}>
            <div className="semaphore-status" style={{ color: getStatusColor(semaphore.drawdown_divergence_status) }}>
              <span className="semaphore-icon">{getStatusIcon(semaphore.drawdown_divergence_status)}</span>
              <span className="semaphore-label">Divergencia Drawdown</span>
            </div>
          </div>
        </div>
      </div>

      {/* Current Hashes */}
      <div className="hashes-section">
        <h3>Hashes Vigentes</h3>
        <div className="hashes-grid">
          <div className="hash-item">
            <label>Code Commit</label>
            <code className="hash-value">{current_hashes.code_commit.substring(0, 16)}...</code>
          </div>
          <div className="hash-item">
            <label>Dataset Version</label>
            <code className="hash-value">{current_hashes.dataset_version.substring(0, 16)}...</code>
          </div>
          <div className="hash-item">
            <label>Params Digest</label>
            <code className="hash-value">{current_hashes.params_digest.substring(0, 16)}...</code>
          </div>
        </div>
      </div>

      {/* Hash Verifications */}
      <div className="verifications-section">
        <h3>Verificaciones de Hashes</h3>
        <div className="verifications-list">
          {hash_verifications.map((v) => (
            <div key={v.hash_type} className="verification-item" style={{ borderLeftColor: getStatusColor(v.status) }}>
              <div className="verification-header">
                <span className="verification-type">{v.hash_type}</span>
                <span className="verification-status" style={{ color: getStatusColor(v.status) }}>
                  {getStatusIcon(v.status)} {v.status.toUpperCase()}
                </span>
              </div>
              <div className="verification-message">{v.message}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Tracking Error Rolling */}
      <div className="tracking-error-section">
        <h3>Tracking Error Rolling</h3>
        <div className="tracking-error-grid">
          {(['7d', '30d', '90d'] as const).map((period) => {
            const te = tracking_error_rolling[period]
            if (!te) {
              return (
                <div key={period} className="tracking-error-card">
                  <h4>{period}</h4>
                  <p>Datos insuficientes</p>
                </div>
              )
            }
            return (
              <div key={period} className="tracking-error-card">
                <h4>{period}</h4>
                <div className="tracking-error-metrics">
                  <div className="metric">
                    <label>Mean Deviation</label>
                    <span>{(te.mean_deviation * 100).toFixed(2)}%</span>
                  </div>
                  <div className="metric">
                    <label>Max Divergence</label>
                    <span>{(te.max_divergence * 100).toFixed(2)}%</span>
                  </div>
                  <div className="metric">
                    <label>Correlation</label>
                    <span>{(te.correlation * 100).toFixed(1)}%</span>
                  </div>
                  <div className="metric">
                    <label>Annualized TE</label>
                    <span className={te.annualized_tracking_error > 5 ? 'warning' : te.annualized_tracking_error > 10 ? 'danger' : 'ok'}>
                      {te.annualized_tracking_error.toFixed(2)}%
                    </span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
        {/* Tracking Error Comparison Chart */}
        <div className="tracking-error-chart">
          <h4>Comparación de Tracking Error por Período</h4>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={[
              { period: '7d', value: tracking_error_rolling['7d']?.annualized_tracking_error || 0 },
              { period: '30d', value: tracking_error_rolling['30d']?.annualized_tracking_error || 0 },
              { period: '90d', value: tracking_error_rolling['90d']?.annualized_tracking_error || 0 },
            ]}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="period" />
              <YAxis label={{ value: 'Tracking Error (%)', angle: -90, position: 'insideLeft' }} />
              <Tooltip formatter={(value: number) => `${value.toFixed(2)}%`} />
              <Legend />
              <Area type="monotone" dataKey="value" stroke="#8884d8" fill="#8884d8" fillOpacity={0.6} name="Annualized TE" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Drawdown Divergence */}
      {drawdown_divergence && (
        <div className="drawdown-section">
          <h3>Divergencia de Drawdown</h3>
          <div className="drawdown-card">
            <div className="drawdown-metrics">
              <div className="metric">
                <label>Max DD Teórico</label>
                <span>{(drawdown_divergence.theoretical_max_dd * 100).toFixed(2)}%</span>
              </div>
              <div className="metric">
                <label>Max DD Realista</label>
                <span>{(drawdown_divergence.realistic_max_dd * 100).toFixed(2)}%</span>
              </div>
              <div className="metric">
                <label>Divergencia</label>
                <span>{drawdown_divergence.divergence_pct.toFixed(2)}%</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Audit Status */}
      <div className="audit-section">
        <h3>Estado de Auditorías</h3>
        <div className="audit-card">
          <div className="audit-metrics">
            <div className="metric">
              <label>Total Exports</label>
              <span>{audit_status.total_exports}</span>
            </div>
            <div className="metric">
              <label>Exports 24h</label>
              <span>{audit_status.recent_exports_24h}</span>
            </div>
            <div className="metric">
              <label>Cambios de Hash</label>
              <span>{audit_status.hash_changes.length}</span>
            </div>
          </div>
          {audit_status.hash_changes.length > 0 && (
            <div className="hash-changes">
              <h4>Últimos Cambios de Hash</h4>
              <ul>
                {audit_status.hash_changes.slice(0, 5).map((change, idx) => (
                  <li key={idx}>
                    <strong>{change.type}</strong>: {change.old.substring(0, 8)} → {change.new.substring(0, 8)} ({new Date(change.timestamp).toLocaleString()})
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

export default TransparencyDashboard

interface ErrorBannerProps {
  statusAlert: DashboardStatusAlert | null
  onRetry: () => void
}

function ErrorBanner({ statusAlert, onRetry }: ErrorBannerProps) {
  const hasAlert = Boolean(statusAlert)
  const guidance =
    'Revisa el estado del backend, vuelve a intentar más tarde o contacta a soporte si el problema persiste.'

  return (
    <div className="error transparency-error-banner" role="alert">
      <p>{statusAlert?.message ?? 'No se pudieron cargar los datos del dashboard.'}</p>
      {statusAlert?.details && <p>{statusAlert.details}</p>}
      <p className="guidance">{guidance}</p>
      <div className="error-meta">
        {statusAlert?.lastAttempt && <small>Último intento: {new Date(statusAlert.lastAttempt).toLocaleString()}</small>}
        {statusAlert?.cacheExpiresAt && (
          <small> | Próximo refresco: {new Date(statusAlert.cacheExpiresAt).toLocaleString()}</small>
        )}
        {typeof statusAlert?.retryAfterSeconds === 'number' && (
          <small> | Reintento automático en ~{statusAlert.retryAfterSeconds}s.</small>
        )}
      </div>
      <div className="error-actions">
        <button type="button" className="refresh-button" onClick={onRetry}>
          🔄 Reintentar
        </button>
        <a href="mailto:soporte@onesmarttrade.com" className="support-link">
          Contactar soporte
        </a>
      </div>
    </div>
  )
}

interface FallbackDataBannerProps {
  message?: string | null
  metadata?: Record<string, any> | null
  fallbackSummary?: FallbackSummary | null
}

function FallbackDataBanner({ message, metadata, fallbackSummary }: FallbackDataBannerProps) {
  const warningMessage =
    message || metadata?.user_message || 'Los datos frescos no están disponibles; mostrando métricas almacenadas.'
  const fallbackSource = fallbackSummary?.source || metadata?.fallback_summary_source || 'Histórico'
  const period = (fallbackSummary?.period || metadata?.period) as
    | { start?: string; end?: string }
    | undefined
  const periodLabel =
    period?.start && period?.end
      ? `${new Date(period.start).toLocaleDateString()} — ${new Date(period.end).toLocaleDateString()}`
      : 'Período no disponible'
  const staleInterval = metadata?.stale_interval || metadata?.interval
  const latestTimestamp = metadata?.latest_timestamp || metadata?.latestTimestamp
  const ageMinutes = metadata?.age_minutes ?? metadata?.latest_candle_age_minutes
  const remediation = metadata?.remediation || metadata?.recovery_hints?.[0]

  return (
    <div className="transparency-stale-banner" role="alert" aria-live="polite">
      <div className="stale-banner-header">
        <span className="stale-indicator">⚠ Datos en modo degradado (stale)</span>
        <strong>{warningMessage}</strong>
      </div>
      <div className="stale-banner-body">
        <div>
          <span className="stale-label">Origen:</span> {fallbackSource}
        </div>
        <div>
          <span className="stale-label">Período:</span> {periodLabel}
        </div>
        {staleInterval && (
          <div>
            <span className="stale-label">Intervalo afectado:</span> {staleInterval}
          </div>
        )}
        {latestTimestamp && (
          <div>
            <span className="stale-label">Último timestamp:</span> {new Date(latestTimestamp).toLocaleString()}
          </div>
        )}
        {typeof ageMinutes === 'number' && (
          <div>
            <span className="stale-label">Antigüedad aprox.:</span> {ageMinutes.toFixed(2)} minutos
          </div>
        )}
        {remediation && (
          <div>
            <span className="stale-label">Acción sugerida:</span> {remediation}
          </div>
        )}
      </div>
    </div>
  )
}

