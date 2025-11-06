import { useQuery } from '@tanstack/react-query'
import { getRecommendationHistory } from '../services/api'
import './HistoryTable.css'

function HistoryTable() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['recommendation', 'history'],
    queryFn: () => getRecommendationHistory(10),
  })

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
      {recommendations.length === 0 ? (
        <div className="empty">No hay historial disponible</div>
      ) : (
        <table className="history-table">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Señal</th>
              <th>Precio</th>
              <th>Confianza</th>
            </tr>
          </thead>
          <tbody>
            {recommendations.map((rec: any, index: number) => (
              <tr key={index}>
                <td>{new Date(rec.timestamp).toLocaleDateString()}</td>
                <td>
                  <span className={`signal-badge signal-${rec.signal.toLowerCase()}`}>
                    {rec.signal}
                  </span>
                </td>
                <td>${rec.current_price.toLocaleString()}</td>
                <td>{rec.confidence.toFixed(1)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export default HistoryTable

