import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Dashboard from '../../pages/Dashboard'

describe('Dashboard smoke', () => {
  it('renders header and refresh button', () => {
    const qc = new QueryClient()
    render(
      <QueryClientProvider client={qc}>
        <Dashboard />
      </QueryClientProvider>
    )
    expect(screen.getByText('One Smart Trade')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Refrescar/i })).toBeInTheDocument()
  })
})


