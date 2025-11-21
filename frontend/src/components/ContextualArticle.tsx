import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/hooks'
import './ContextualArticle.css'

interface ContextualArticle {
  id: number
  title: string
  slug: string
  summary: string
  category: string
  micro_habits?: string[]
  is_critical?: boolean
}

interface ContextualArticleProps {
  article: ContextualArticle
  userId: string
  onDismiss?: () => void
}

export function ContextualArticle({ article, userId, onDismiss }: ContextualArticleProps) {
  const [isExpanded, setIsExpanded] = useState(false)
  const [isReading, setIsReading] = useState(false)
  const queryClient = useQueryClient()

  const { data: articleData, isLoading } = useQuery({
    queryKey: ['knowledge-article', article.slug],
    queryFn: async ({ signal }) => {
      const { data } = await api.get(`/api/v1/knowledge/articles/${article.slug}`, {
        params: { user_id: userId, mark_as_read: true },
        signal,
      })
      return data.article
    },
    enabled: isExpanded && isReading,
    staleTime: 3600000, // 1 hour
  })

  const handleRead = () => {
    if (!isExpanded) {
      setIsExpanded(true)
      setIsReading(true)
    } else {
      setIsExpanded(false)
      setIsReading(false)
    }
  }

  const handleDownloadPDF = async () => {
    try {
      const response = await api.get(`/api/v1/knowledge/articles/${article.slug}/pdf`, {
        params: { user_id: userId },
        responseType: 'blob',
      })
      const blob = new Blob([response.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${article.slug}.pdf`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (error) {
      console.error('Error downloading PDF:', error)
    }
  }

  const completeMutation = useMutation({
    mutationFn: async () => {
      await api.post(`/api/v1/knowledge/articles/${article.slug}/complete`, null, {
        params: { user_id: userId },
      })
    },
    onSuccess: () => {
      // Optionally refresh article data or show success message
      queryClient.invalidateQueries({ queryKey: ['knowledge-article', article.slug] })
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

  return (
    <div className="contextual-article">
      <div className="article-header">
        <div className="article-category">{getCategoryLabel(article.category)}</div>
        {onDismiss && (
          <button className="article-dismiss" onClick={onDismiss} aria-label="Cerrar artículo">
            ×
          </button>
        )}
      </div>
      <h3 className="article-title">
        {article.title}
        {article.is_critical && <span className="article-critical-badge">⚠️ Crítico</span>}
      </h3>
      <p className="article-summary">{article.summary}</p>
      {article.micro_habits && article.micro_habits.length > 0 && (
        <div className="article-micro-habits">
          <h4 className="micro-habits-title">Micro-hábitos recomendados:</h4>
          <ul className="micro-habits-list">
            {article.micro_habits.map((habit, index) => (
              <li key={index}>{habit}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="article-actions">
        <button className="btn-read" onClick={handleRead}>
          {isExpanded ? 'Ocultar artículo' : 'Leer artículo'}
        </button>
        {articleData?.has_pdf && (
          <button className="btn-download-pdf" onClick={handleDownloadPDF}>
            📄 Descargar PDF
          </button>
        )}
        <button
          className="btn-complete"
          onClick={() => completeMutation.mutate()}
          disabled={completeMutation.isPending}
        >
          {completeMutation.isPending ? 'Marcando...' : '✓ Marcar como completado'}
        </button>
      </div>
      {isExpanded && (
        <div className="article-content">
          {isLoading ? (
            <div className="loading-spinner">Cargando artículo...</div>
          ) : articleData ? (
            <div
              className="article-body"
              dangerouslySetInnerHTML={{ __html: articleData.content.replace(/\n/g, '<br />') }}
            />
          ) : (
            <p>Error al cargar el artículo</p>
          )}
        </div>
      )}
    </div>
  )
}

interface ContextualArticlesProps {
  articles: ContextualArticle[]
  userId: string
  title?: string
  onDismiss?: () => void
}

export function ContextualArticles({ articles, userId, title = "Artículos Recomendados", onDismiss }: ContextualArticlesProps) {
  if (!articles || articles.length === 0) {
    return null
  }

  return (
    <div className="contextual-articles-section">
      <h3 className="section-title">{title}</h3>
      <p className="section-description">
        Basado en tu situación actual, estos artículos pueden ayudarte a mejorar tu gestión de riesgo y toma de decisiones.
      </p>
      <div className="articles-list">
        {articles.map((article) => (
          <ContextualArticle key={article.id} article={article} userId={userId} onDismiss={onDismiss} />
        ))}
      </div>
    </div>
  )
}

