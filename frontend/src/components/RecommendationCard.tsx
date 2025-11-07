import { useState } from 'react'
import { useInvalidateAll, useTodayRecommendation } from '../api/hooks'
import './RecommendationCard.css'

function RecommendationCard() {
  const [isRetrying, setIsRetrying] = useState(false)
  const { data, isLoading, error, refetch, isRefetching } = useTodayRecommendation()
  const invalidateAll = useInvalidateAll()

  const handleRetry = async () => {
    setIsRetrying(true)
    try {
      // Invalidate all queries first to clear cache
      await invalidateAll()
      // Then refetch the current query
      await refetch()
    } catch (err) {
      console.error('Error retrying recommendation:', err)
    } finally {
      setIsRetrying(false)
    }
  }

  if (isLoading || isRefetching || isRetrying) {
    return (
      <div className="recommendation-card loading" role="status" aria-live="polite">
        <div className="loading-spinner">
          {isRetrying ? 'Reintentando...' : 'Cargando recomendación...'}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="recommendation-card error" role="alert" aria-live="assertive">
        <p>Error al cargar recomendación</p>
        <button 
          onClick={handleRetry} 
          type="button" 
          aria-label="Reintentar carga"
          disabled={isRetrying}
        >
          {isRetrying ? 'Reintentando...' : 'Reintentar'}
        </button>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="recommendation-card">
        <p>No hay recomendación disponible</p>
      </div>
    )
  }

  const signalClass = `signal-${data.signal.toLowerCase()}`

  return (
    <div className="recommendation-card">
      <div className="recommendation-header" aria-label="Señal actual">
        <h2>Recomendación de Hoy</h2>
        <span className={`signal-badge ${signalClass}`}>{data.signal}</span>
      </div>
      <div className="recommendation-content">
        <div className="price-info">
          <span className="label">Precio Actual:</span>
          <span className="value">${data.current_price.toLocaleString()}</span>
        </div>
        <div className="entry-range">
          <span className="label">Rango de Entrada:</span>
          <span className="value">
            ${data.entry_range.min.toLocaleString()} - ${data.entry_range.max.toLocaleString()}
          </span>
        </div>
        <div className="sl-tp">
          <div className="sl-tp-item">
            <span className="label">Stop Loss:</span>
            <span className="value danger">${data.stop_loss_take_profit.stop_loss.toLocaleString()}</span>
          </div>
          <div className="sl-tp-item">
            <span className="label">Take Profit:</span>
            <span className="value success">${data.stop_loss_take_profit.take_profit.toLocaleString()}</span>
          </div>
        </div>
        <div className="confidence">
          <span className="label">Confianza:</span>
          <span className="value">{data.confidence.toFixed(1)}%</span>
        </div>
        <section aria-labelledby="analysis-heading" className="analysis">
          <h3 id="analysis-heading">Análisis profesional</h3>
          <p className="analysis-text">{data.analysis}</p>
        </section>
        {data.disclaimer && (
          <div className="recommendation-disclaimer" role="note" aria-label="Disclaimer legal">
            <strong>⚠️ Aviso Legal:</strong> {data.disclaimer}
          </div>
        )}
      </div>
    </div>
  )
}

export default RecommendationCard

