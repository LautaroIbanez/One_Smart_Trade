import './DegradedDataBanner.css'

interface DegradedDataBannerProps {
  message?: string
  source?: string
  cachedAt?: string
}

export function DegradedDataBanner({ 
  message = 'Mostrando datos almacenados en lugar de datos frescos.', 
  source,
  cachedAt 
}: DegradedDataBannerProps) {
  return (
    <div className="degraded-data-banner" role="status" aria-live="polite">
      <span className="banner-icon">⚠️</span>
      <div className="banner-content">
        <strong>Modo degradado:</strong> {message}
        {(source || cachedAt) && (
          <small className="banner-meta">
            {source && `Fuente: ${source}`}
            {cachedAt && ` | Cached: ${new Date(cachedAt).toLocaleString()}`}
          </small>
        )}
      </div>
    </div>
  )
}

