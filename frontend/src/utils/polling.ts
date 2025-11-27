/**
 * Centralized polling configuration to prevent redundant requests.
 * 
 * Implements status-based polling intervals with jitter to prevent
 * thundering herd and parallel duplicate requests.
 */

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
 * Returns interval with ±20% random jitter.
 */
export function addJitter(baseInterval: number, jitterPercent: number = 0.2): number {
  const jitter = baseInterval * jitterPercent
  const randomOffset = (Math.random() * 2 - 1) * jitter // -jitter to +jitter
  return Math.max(1000, baseInterval + randomOffset) // Minimum 1 second
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

