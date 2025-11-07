import { useRecommendationHistory } from '../api/hooks'
import './HistoryTable.css'

function HistoryTable() {
  const { data, isLoading, error } = useRecommendationHistory(10)

  if (isLoading) {
    return (
      <div className="history-table-container">
        <h2>Historial Reciente</h2>
        <div className="loading">Cargando...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="history-table-container">
        <h2>Historial Reciente</h2>
        <div className="error">Error al cargar historial</div>
      </div>
    )
  }

  const recommendations = data?.recommendations || []

  return (
    <div className="history-table-container">
      <h2>Historial Reciente</h2>
      {isLoading ? (
        <div className="loading" role="status" aria-live="polite">Cargando historial...</div>
      ) : error ? (
        <div className="error" role="alert">Error al cargar historial</div>
      ) : recommendations.length === 0 ? (
        <div className="empty">No hay historial disponible</div>
      ) : (
        <div className="table-wrapper">
          <table className="history-table" aria-label="Historial de recomendaciones">
            <thead>
              <tr>
                <th scope="col">Fecha</th>
                <th scope="col">Señal</th>
                <th scope="col">Precio</th>
                <th scope="col">Confianza</th>
              </tr>
            </thead>
            <tbody>
              {recommendations.map((rec: { timestamp: string; signal: string; current_price: number; confidence: number }, index: number) => (
                <tr key={rec.timestamp || index}>
                  <td>{new Date(rec.timestamp).toLocaleDateString('es-ES')}</td>
                  <td>
                    <span className={`signal-badge signal-${rec.signal.toLowerCase()}`} aria-label={`Señal: ${rec.signal}`}>
                      {rec.signal}
                    </span>
                  </td>
                  <td>${rec.current_price.toLocaleString()}</td>
                  <td>{rec.confidence.toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default HistoryTable

