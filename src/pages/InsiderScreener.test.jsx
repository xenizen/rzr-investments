import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import InsiderScreener from './InsiderScreener'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('InsiderScreener', () => {
  it('renders the page heading', () => {
    render(<InsiderScreener />)
    expect(screen.getByRole('heading', { name: 'Insider Screener' })).toBeInTheDocument()
  })

  it('renders the "not investment advice" disclaimer', () => {
    render(<InsiderScreener />)
    expect(screen.getByText(/not investment advice/i)).toBeInTheDocument()
  })

  it('renders the parameter-form and results placeholders for later stories to fill', () => {
    render(<InsiderScreener />)
    expect(document.getElementById('screenerForm')).toBeInTheDocument()
    expect(document.getElementById('screenerResults')).toBeInTheDocument()
  })

  it('makes no backend call on mount', () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
    render(<InsiderScreener />)
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
