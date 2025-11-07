import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@testing-library/jest-dom/vitest'
import Dashboard from '../../pages/Dashboard'

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('Dashboard smoke', () => {
  it('renders header and refresh button', () => {
    render(<Dashboard />, { wrapper: createWrapper() })
    // There are two "One Smart Trade" headings (AppLayout and Dashboard), so use getAllByText
    expect(screen.getAllByText('One Smart Trade').length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /Refrescar/i })).toBeInTheDocument()
  })

  it('renders all main sections', () => {
    render(<Dashboard />, { wrapper: createWrapper() })
    // RecommendationCard shows loading state initially, so check for loading text or section
    expect(screen.getByText(/Cargando recomendación/i)).toBeInTheDocument()
    expect(screen.getByText(/Indicadores Clave/i)).toBeInTheDocument()
    expect(screen.getByText(/Historial Reciente/i)).toBeInTheDocument()
  })
})


