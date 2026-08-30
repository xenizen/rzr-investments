import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import InsiderScreener from './InsiderScreener'

afterEach(() => {
  vi.unstubAllGlobals()
})

function jsonResponse(body) {
  return { json: () => Promise.resolve(body) }
}

function runScreen() {
  fireEvent.click(screen.getByRole('button', { name: /run screen/i }))
}

describe('InsiderScreener', () => {
  it('renders the page heading and disclaimer', () => {
    render(<InsiderScreener />)
    expect(screen.getByRole('heading', { name: 'Insider Screener' })).toBeInTheDocument()
    expect(screen.getByText(/not investment advice/i)).toBeInTheDocument()
  })

  it('renders the four parameter dropdowns with the expected options and defaults', () => {
    render(<InsiderScreener />)

    const direction = document.getElementById('selScreenerDirection')
    expect([...direction.options].map((o) => o.value)).toEqual(['Purchase', 'Sold'])
    expect(direction.value).toBe('Purchase')

    const shares = document.getElementById('selScreenerShares')
    expect([...shares.options].map((o) => o.value)).toEqual(['5000', '10000', '15000', '20000'])
    expect(shares.value).toBe('10000')

    const months = document.getElementById('selScreenerMonths')
    expect([...months.options].map((o) => o.value)).toEqual(['1', '2', '3', '4', '5', '6'])
    expect(months.value).toBe('1')

    const pct = document.getElementById('selScreenerPct')
    expect([...pct.options].map((o) => o.value)).toEqual(['50', '60', '70', '80', '90', '100'])
    expect(pct.value).toBe('70')
  })

  it('does not call the backend on mount', () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
    render(<InsiderScreener />)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('fires one request with the selected parameters when Run screen is clicked', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ results: [], total_count: 0, page: 1, has_next: false }))
    vi.stubGlobal('fetch', fetchMock)
    render(<InsiderScreener />)

    fireEvent.change(document.getElementById('selScreenerDirection'), { target: { value: 'Sold' } })
    fireEvent.change(document.getElementById('selScreenerShares'), { target: { value: '15000' } })
    fireEvent.change(document.getElementById('selScreenerMonths'), { target: { value: '3' } })
    fireEvent.change(document.getElementById('selScreenerPct'), { target: { value: '80' } })
    runScreen()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/insider-screener?direction=Sold&shares=15000&months=3&pct_below_high=80',
    )
    expect(await screen.findByText('No matches for these parameters.')).toBeInTheDocument()
  })

  it('uses the defaults when nothing is changed', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ results: [], total_count: 0, page: 1, has_next: false }))
    vi.stubGlobal('fetch', fetchMock)
    render(<InsiderScreener />)

    runScreen()

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/insider-screener?direction=Purchase&shares=10000&months=1&pct_below_high=70',
    )
  })

  it('shows a screening indicator and disables the button while the request is in flight', async () => {
    let resolveFetch
    vi.stubGlobal(
      'fetch',
      vi.fn().mockReturnValue(new Promise((resolve) => { resolveFetch = resolve })),
    )
    render(<InsiderScreener />)

    runScreen()

    expect(await screen.findByText('Screening…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run screen/i })).toBeDisabled()

    resolveFetch(jsonResponse({ results: [], total_count: 0, page: 1, has_next: false }))

    expect(await screen.findByText('No matches for these parameters.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run screen/i })).toBeEnabled()
  })

  it('lists matching tickers and shows a count', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          results: [
            { ticker: 'TRDA', side: 'sell', discount_pct: 55.7, multiple_insiders: true },
            { ticker: 'SNES', side: 'buy', discount_pct: 79.5, multiple_insiders: false },
          ],
          total_count: 2,
          page: 1,
          has_next: false,
        }),
      ),
    )
    render(<InsiderScreener />)

    runScreen()

    expect(await screen.findByText('2 matches')).toBeInTheDocument()
    const rows = screen.getAllByTestId('screener-result-row')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('TRDA · sell · 55.7% below high · multiple insiders')
    expect(rows[1]).not.toHaveTextContent('multiple insiders')
  })

  it('shows the backend error message on a failed screen', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ error: 'The screener is temporarily unavailable.' })),
    )
    render(<InsiderScreener />)

    runScreen()

    expect(await screen.findByText('The screener is temporarily unavailable.')).toBeInTheDocument()
    expect(screen.queryByTestId('screener-result-row')).not.toBeInTheDocument()
  })

  it('shows a fallback message when the request itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')))
    render(<InsiderScreener />)

    runScreen()

    expect(await screen.findByText('Something went wrong running the screen.')).toBeInTheDocument()
  })
})
