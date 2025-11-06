import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'
import Dashboard from '../../pages/Dashboard'

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('Dashboard Integration', () => {
  it('renders header and refresh button', () => {
    render(<Dashboard />, { wrapper: createWrapper() })
    expect(screen.getByText('One Smart Trade')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Refrescar/i })).toBeInTheDocument()
  })

  it('refresh button invalidates queries', async () => {
    const user = userEvent.setup()
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    const Wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    render(<Dashboard />, { wrapper: Wrapper })
    const refreshButton = screen.getByRole('button', { name: /Refrescar/i })
    await user.click(refreshButton)

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalled()
    })
  })
})

