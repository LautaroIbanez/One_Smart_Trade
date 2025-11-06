import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
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
    expect(screen.getByText('One Smart Trade')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Refrescar/i })).toBeInTheDocument()
  })

  it('renders all main sections', () => {
    render(<Dashboard />, { wrapper: createWrapper() })
    expect(screen.getByText(/Recomendación de Hoy/i)).toBeInTheDocument()
    expect(screen.getByText(/Indicadores Clave/i)).toBeInTheDocument()
    expect(screen.getByText(/Historial Reciente/i)).toBeInTheDocument()
  })
})


