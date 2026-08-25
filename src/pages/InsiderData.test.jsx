import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import InsiderData from './InsiderData'

afterEach(() => {
  vi.unstubAllGlobals()
})

function fillField(id, value) {
  fireEvent.change(document.getElementById(id), { target: { value } })
}

function fillAndSearch({ symbol, name, dateFrom, dateTo } = {}) {
  if (symbol !== undefined) fillField('txtInsiderSymbol', symbol)
  if (name !== undefined) fillField('txtInsiderName', name)
  if (dateFrom !== undefined) fillField('txtInsiderDateFrom', dateFrom)
  if (dateTo !== undefined) fillField('txtInsiderDateTo', dateTo)
  fireEvent.click(screen.getByRole('button', { name: /search/i }))
}

describe('InsiderData', () => {
  it('renders the symbol, name, and date range inputs', () => {
    render(<InsiderData />)

    const symbol = document.getElementById('txtInsiderSymbol')
    expect(symbol).toBeInTheDocument()
    expect(symbol).toHaveAttribute('type', 'text')

    const name = document.getElementById('txtInsiderName')
    expect(name).toBeInTheDocument()
    expect(name).toHaveAttribute('type', 'text')

    const dateFrom = document.getElementById('txtInsiderDateFrom')
    expect(dateFrom).toBeInTheDocument()
    expect(dateFrom).toHaveAttribute('type', 'date')

    const dateTo = document.getElementById('txtInsiderDateTo')
    expect(dateTo).toBeInTheDocument()
    expect(dateTo).toHaveAttribute('type', 'date')
  })

  it('renders the search button', () => {
    render(<InsiderData />)
    const button = screen.getByRole('button', { name: /search/i })
    expect(button).toBeInTheDocument()
    expect(button).toHaveAttribute('id', 'btnSearchInsider')
  })

  it('shows "no criteria entered" and does not call the API when everything is blank', () => {
    vi.stubGlobal('fetch', vi.fn())
    render(<InsiderData />)

    fillAndSearch()

    expect(screen.getByText('No Search Criteria Entered')).toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('treats whitespace-only text fields as blank', () => {
    vi.stubGlobal('fetch', vi.fn())
    render(<InsiderData />)

    fillAndSearch({ symbol: '   ', name: '  ' })

    expect(screen.getByText('No Search Criteria Entered')).toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('searches by symbol alone and renders the results', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        json: () =>
          Promise.resolve({
            results: [{ insider_name: 'Jane Doe', net_change: 10000, issuer: 'BKKT', filing_date: '2026-08-01' }],
            page: 1,
            total_count: 1,
            has_next: false,
          }),
      }),
    )
    render(<InsiderData />)

    fillAndSearch({ symbol: 'BKKT' })

    expect(await screen.findByTestId('insider-result-row')).toHaveTextContent('Jane Doe')
    expect(fetch).toHaveBeenCalledWith('/api/insider-data?symbol=BKKT')
  })

  it('combines symbol, name, and date range into the query string', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ results: [], page: 1, total_count: 0, has_next: false }),
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<InsiderData />)

    fillAndSearch({ symbol: 'bkkt', name: 'Jane', dateFrom: '2026-01-01', dateTo: '2026-02-01' })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/insider-data?symbol=bkkt&name=Jane&date_from=2026-01-01&date_to=2026-02-01',
    )
  })

  it('shows the backend error message when the search fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ json: () => Promise.resolve({ error: 'No Insider Data Found: Real Stock?' }) }),
    )
    render(<InsiderData />)

    fillAndSearch({ symbol: 'ZZZZZ' })

    expect(await screen.findByText('No Insider Data Found: Real Stock?')).toBeInTheDocument()
  })

  it('shows a friendly message when the search succeeds with no matches', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        json: () => Promise.resolve({ results: [], page: 1, total_count: 0, has_next: false }),
      }),
    )
    render(<InsiderData />)

    fillAndSearch({ name: 'nobody matches this' })

    expect(await screen.findByText('No matching insider filings found.')).toBeInTheDocument()
  })

  it('shows a fallback error message if the request itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')))
    render(<InsiderData />)

    fillAndSearch({ symbol: 'AAPL' })

    expect(await screen.findByText('No Insider Data Found: Real Stock?')).toBeInTheDocument()
  })
})
