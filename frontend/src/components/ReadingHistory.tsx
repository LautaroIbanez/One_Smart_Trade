import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../services/api'
import './ReadingHistory.css'

interface ReadingHistoryProps {
  userId: string
}

interface Article {
  id: number
  title: string
  slug: string
  category: string
  summary: string | null
}

interface Reading {
  id: number
  article_id: number
  article: Article | null
  first_read_at: string | null
  last_read_at: string | null
  read_count: number
  pdf_downloaded: boolean
  pdf_downloaded_at: string | null
  completed: boolean
  completed_at: string | null
}

export function ReadingHistory({ userId }: ReadingHistoryProps) {
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['reading-history', userId],
    queryFn: async () => {
      const { data } = await api.get('/api/v1/knowledge/readings/history', {
        params: { user_id: userId, limit: 50 },
      })
      return data.readings as Reading[]
    },
    staleTime: 30000, // 30 seconds
  })

  const completeMutation = useMutation({
    mutationFn: async (slug: string) => {
      await api.post(`/api/v1/knowledge/articles/${slug}/complete`, null, {
        params: { user_id: userId },
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['reading-history', userId] })
    },
  })

  const getCategoryLabel = (category: string) => {
    const labels: Record<string, string> = {
      emotional_management: 'Gestión Emocional',
      risk_limits: 'Límites de Riesgo',
      rest: 'Descanso',
      journaling: 'Journaling',
    }
    return labels[category] || category
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'N/A'
    const date = new Date(dateString)
    return date.toLocaleDateString('es-ES', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  if (isLoading) {
    return (
      <div className="reading-history">
        <h2>Historial de Lectura</h2>
        <div className="loading-spinner">Cargando historial...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="reading-history">
        <h2>Historial de Lectura</h2>
        <div className="error-message">Error al cargar el historial de lectura</div>
      </div>
    )
  }

  if (!data || data.length === 0) {
    return (
      <div className="reading-history">
        <h2>Historial de Lectura</h2>
        <div className="empty-state">
          <p>No has leído ningún artículo aún.</p>
          <p className="empty-state-hint">Los artículos que leas aparecerán aquí.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="reading-history">
      <h2>Historial de Lectura</h2>
      <p className="reading-history-description">
        Aquí puedes ver todos los artículos educativos que has leído, con información sobre cuándo los leíste y si los completaste.
      </p>
      <div className="readings-list">
        {data.map((reading) => (
          <div key={reading.id} className={`reading-item ${reading.completed ? 'completed' : ''}`}>
            {reading.article ? (
              <>
                <div className="reading-item-header">
                  <div className="reading-item-title-section">
                    <h3 className="reading-item-title">{reading.article.title}</h3>
                    <span className="reading-item-category">{getCategoryLabel(reading.article.category)}</span>
                  </div>
                  {reading.completed && (
                    <span className="reading-item-completed-badge">✓ Completado</span>
                  )}
                </div>
                {reading.article.summary && (
                  <p className="reading-item-summary">{reading.article.summary}</p>
                )}
                <div className="reading-item-stats">
                  <div className="reading-stat">
                    <span className="stat-label">Primera lectura:</span>
                    <span className="stat-value">{formatDate(reading.first_read_at)}</span>
                  </div>
                  <div className="reading-stat">
                    <span className="stat-label">Última lectura:</span>
                    <span className="stat-value">{formatDate(reading.last_read_at)}</span>
                  </div>
                  <div className="reading-stat">
                    <span className="stat-label">Veces leído:</span>
                    <span className="stat-value">{reading.read_count}</span>
                  </div>
                  {reading.pdf_downloaded && (
                    <div className="reading-stat">
                      <span className="stat-label">PDF descargado:</span>
                      <span className="stat-value">{formatDate(reading.pdf_downloaded_at)}</span>
                    </div>
                  )}
                  {reading.completed && reading.completed_at && (
                    <div className="reading-stat">
                      <span className="stat-label">Completado:</span>
                      <span className="stat-value">{formatDate(reading.completed_at)}</span>
                    </div>
                  )}
                </div>
                <div className="reading-item-actions">
                  {!reading.completed && (
                    <button
                      className="btn-complete"
                      onClick={() => completeMutation.mutate(reading.article!.slug)}
                      disabled={completeMutation.isPending}
                    >
                      {completeMutation.isPending ? 'Marcando...' : 'Marcar como completado'}
                    </button>
                  )}
                  <a
                    href={`/api/v1/knowledge/articles/${reading.article.slug}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-read-again"
                  >
                    Leer de nuevo
                  </a>
                </div>
              </>
            ) : (
              <div className="reading-item-error">
                <p>Artículo no encontrado (ID: {reading.article_id})</p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

