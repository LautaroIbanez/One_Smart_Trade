import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import RecommendationCard from '../RecommendationCard'

describe('RecommendationCard', () => {
  it('renders loading state', () => {
    render(<RecommendationCard />)
    expect(screen.getByText(/Cargando recomendación/i)).toBeInTheDocument()
  })
})

