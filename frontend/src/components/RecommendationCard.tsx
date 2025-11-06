import { useInvalidateAll, useTodayRecommendation } from '../api/hooks'
import './RecommendationCard.css'

function RecommendationCard() {
  const { data, isLoading, error, refetch } = useTodayRecommendation()
  const invalidateAll = useInvalidateAll()

  if (isLoading) {
    return (
      <div className="recommendation-card loading">
        <div className="loading-spinner">Cargando recomendación...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="recommendation-card error" role="alert" aria-live="assertive">
        <p>Error al cargar recomendación</p>
        <button onClick={() => invalidateAll()}>Reintentar</button>
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
        <div className="analysis">
          <h3>Análisis</h3>
          <p>{data.analysis}</p>
        </div>
      </div>
    </div>
  )
}

export default RecommendationCard

