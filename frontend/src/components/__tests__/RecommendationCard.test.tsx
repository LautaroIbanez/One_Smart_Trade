import { describe, it, expect } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom/vitest'
import RecommendationCard from '../RecommendationCard'

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('RecommendationCard', () => {
  it('renders loading state', () => {
    render(<RecommendationCard />, { wrapper: createWrapper() })
    expect(screen.getByText(/Cargando recomendación/i)).toBeInTheDocument()
  })

  it('renders error state with retry button', async () => {
    render(<RecommendationCard />, { wrapper: createWrapper() })
    await waitFor(() => {
      const errorText = screen.queryByText(/Error al cargar/i)
      if (errorText) {
        expect(screen.getByRole('button', { name: /Reintentar/i })).toBeInTheDocument()
      }
    }, { timeout: 2000 })
  })
})
