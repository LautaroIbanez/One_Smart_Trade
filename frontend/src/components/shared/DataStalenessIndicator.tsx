import { useMemo } from 'react'
import './DataStalenessIndicator.css'

interface DataStalenessIndicatorProps {
  /** Timestamp of the last candle (ISO string) */
  asOf?: string | null
  /** Age of data in minutes */
  ageMinutes?: number | null
  /** Whether data is marked as stale by backend */
  isStale?: boolean
  /** Status from backend (e.g., 'data_stale', 'success') */
  status?: string
  /** Optional interval being displayed */
  interval?: string
}

/**
 * FE-UX-02: Component to display data staleness indicator near charts.
 * Shows last candle timestamp and data age to make stale data visible.
 */
export function DataStalenessIndicator({
  asOf,
  ageMinutes,
  isStale = false,
  status,
  interval,
}: DataStalenessIndicatorProps) {
  const stalenessInfo = useMemo(() => {
    // Determine staleness level
    let level: 'fresh' | 'recent' | 'aging' | 'stale' = 'fresh'
    let label = 'Datos frescos'
    let icon = '✅'
    let className = 'staleness-fresh'

    if (isStale || status === 'data_stale') {
      level = 'stale'
      label = 'Datos desactualizados'
      icon = '⚠️'
      className = 'staleness-stale'
    } else if (ageMinutes !== null && ageMinutes !== undefined) {
      if (ageMinutes <= 15) {
        level = 'fresh'
        label = 'Datos frescos'
        icon = '✅'
        className = 'staleness-fresh'
      } else if (ageMinutes <= 60) {
        level = 'recent'
        label = 'Datos recientes'
        icon = '🕐'
        className = 'staleness-recent'
      } else if (ageMinutes <= 240) {
        level = 'aging'
        label = 'Datos envejeciendo'
        icon = '⏰'
        className = 'staleness-aging'
      } else {
        level = 'stale'
        label = 'Datos desactualizados'
        icon = '⚠️'
        className = 'staleness-stale'
      }
    }

    // Format age text
    let ageText = ''
    if (ageMinutes !== null && ageMinutes !== undefined) {
      if (ageMinutes < 1) {
        ageText = 'menos de 1 minuto'
      } else if (ageMinutes < 60) {
        ageText = `hace ${Math.round(ageMinutes)} ${Math.round(ageMinutes) === 1 ? 'minuto' : 'minutos'}`
      } else if (ageMinutes < 1440) {
        const hours = Math.floor(ageMinutes / 60)
        const mins = Math.round(ageMinutes % 60)
        if (mins === 0) {
          ageText = `hace ${hours} ${hours === 1 ? 'hora' : 'horas'}`
        } else {
          ageText = `hace ${hours}h ${mins}m`
        }
      } else {
        const days = Math.floor(ageMinutes / 1440)
        const hours = Math.floor((ageMinutes % 1440) / 60)
        if (hours === 0) {
          ageText = `hace ${days} ${days === 1 ? 'día' : 'días'}`
        } else {
          ageText = `hace ${days}d ${hours}h`
        }
      }
    }

    // Format timestamp
    let timestampText = ''
    if (asOf) {
      try {
        const date = new Date(asOf)
        const now = new Date()
        const diffMs = now.getTime() - date.getTime()
        const diffMins = diffMs / (1000 * 60)

        // If timestamp is very recent (< 5 minutes), show relative time
        if (diffMins < 5) {
          timestampText = 'hace un momento'
        } else {
          // Show formatted date/time
          timestampText = date.toLocaleString('es-ES', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          })
        }
      } catch {
        timestampText = asOf
      }
    }

    return {
      level,
      label,
      icon,
      className,
      ageText,
      timestampText,
    }
  }, [asOf, ageMinutes, isStale, status])

  // FE-UX-02: Don't render if no data available, but show placeholder if we're waiting for data
  // This ensures the indicator appears as soon as data is available
  if (!asOf && (ageMinutes === null || ageMinutes === undefined)) {
    return null
  }

  return (
    <div className={`data-staleness-indicator ${stalenessInfo.className}`} role="status" aria-live="polite">
      <span className="staleness-icon" aria-hidden="true">
        {stalenessInfo.icon}
      </span>
      <div className="staleness-content">
        <div className="staleness-label">
          <strong>{stalenessInfo.label}</strong>
          {interval && <span className="staleness-interval">({interval})</span>}
        </div>
        <div className="staleness-details">
          {stalenessInfo.ageText && (
            <span className="staleness-age">
              {stalenessInfo.ageText}
            </span>
          )}
          {stalenessInfo.timestampText && (
            <span className="staleness-timestamp">
              Última vela: {stalenessInfo.timestampText}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

