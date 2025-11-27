/**
 * Centralized polling configuration to prevent redundant requests.
 *
 * Expose a single source of truth for dashboard/query refetch cadence so we can
 * adjust behaviour per-environment (dev vs prod vs tests) without touching every component.
 */

type RuntimeEnv = 'development' | 'production' | 'test'

function resolveRuntimeEnv(): RuntimeEnv {
  // Vite exposes import.meta.env.MODE, Vitest falls back to NODE_ENV
  if (typeof import.meta !== 'undefined' && import.meta.env?.MODE) {
    return (import.meta.env.MODE as RuntimeEnv) || 'development'
  }
  if (typeof process !== 'undefined' && process.env?.NODE_ENV) {
    return (process.env.NODE_ENV as RuntimeEnv) || 'development'
  }
  return 'development'
}

const runtimeEnv = resolveRuntimeEnv()

const ENV_MULTIPLIERS: Record<RuntimeEnv, number> = {
  development: 0.6, // faster feedback in dev
  production: 1,
  test: 0.1, // keep tests fast without disabling timers entirely
}

/**
 * Update this object when tweaking default dashboard polling cadence.
 * Documented here so future changes remain localized.
 */
export const pollingConfig = {
  env: runtimeEnv,
  multiplier: ENV_MULTIPLIERS[runtimeEnv] ?? 1,
  minIntervalMs: runtimeEnv === 'development' ? 750 : 1000,
  maxIntervalMs: 600_000,
  docs:
    'Dashboard widgets derive all refetch intervals from this config. Adjust multiplier/min/max to tune cadence per environment.',
}

const clampInterval = (value: number) =>
  Math.min(pollingConfig.maxIntervalMs, Math.max(pollingConfig.minIntervalMs, value))

/**
 * Polling intervals based on data status.
 * When status is stable (not degraded/processing), polling slows significantly.
 */
export const POLLING_INTERVALS = {
  // Fast polling for degraded/processing states
  DEGRADED: 10_000, // 10 seconds
  PROCESSING: 10_000, // 10 seconds

  // Normal polling for active data
  ACTIVE: 60_000, // 1 minute

  // Slow polling for stable/cached data
  STABLE: 300_000, // 5 minutes

  // Very slow polling for static data
  STATIC: 600_000, // 10 minutes
} as const

/**
 * Add jitter to polling interval to prevent parallel requests.
 * Returns interval with ±20% random jitter and applies environment scaling.
 */
export function addJitter(baseInterval: number, jitterPercent: number = 0.2): number {
  const scaledBase = baseInterval * pollingConfig.multiplier
  const jitter = scaledBase * jitterPercent
  const randomOffset = (Math.random() * 2 - 1) * jitter // -jitter to +jitter
  return clampInterval(scaledBase + randomOffset)
}

/**
 * Determine polling interval based on data status.
 * Returns false to disable polling if data is stable and cached.
 */
export function getPollingInterval(
  status: string | undefined | null,
  isStale: boolean = false,
  cacheAge?: number
): number | false {
  // If status is degraded or processing, poll frequently
  if (status === 'degraded' || status === 'processing') {
    return addJitter(POLLING_INTERVALS.DEGRADED)
  }
  
  // If data is stale (needs refresh), poll at normal interval
  if (isStale) {
    return addJitter(POLLING_INTERVALS.ACTIVE)
  }
  
  // If data is cached and recent (< 2 minutes), slow polling significantly
  if (cacheAge !== undefined && cacheAge < 120_000) {
    return addJitter(POLLING_INTERVALS.STABLE)
  }
  
  // If status is success/stable, use slow polling
  if (status === 'success' || status === 'pass') {
    return addJitter(POLLING_INTERVALS.STABLE)
  }
  
  // Default: normal polling
  return addJitter(POLLING_INTERVALS.ACTIVE)
}

/**
 * Check if data status indicates active processing that requires frequent polling.
 */
export function requiresFastPolling(status: string | undefined | null): boolean {
  return status === 'degraded' || status === 'processing' || status === 'error'
}


