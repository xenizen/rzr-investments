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

function jsonResponse(body) {
  return { json: () => Promise.resolve(body) }
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

  it('searches by symbol alone and renders the results in a table', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          results: [{ insider_name: 'Jane Doe', net_change: 10000, issuer: 'BKKT', filing_date: '2026-08-01' }],
          page: 1,
          total_count: 1,
          has_next: false,
        }),
      ),
    )
    render(<InsiderData />)

    fillAndSearch({ symbol: 'BKKT' })

    expect(await screen.findByTestId('insider-result-row')).toHaveTextContent('Jane Doe')
    expect(fetch).toHaveBeenCalledWith('/api/insider-data?symbol=BKKT')
  })

  it('renders the expected table column headers', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          results: [{ insider_name: 'Jane Doe', net_change: 10000, issuer: 'BKKT', filing_date: '2026-08-01' }],
          page: 1,
          total_count: 1,
          has_next: false,
        }),
      ),
    )
    render(<InsiderData />)

    fillAndSearch({ symbol: 'BKKT' })
    await screen.findByTestId('insider-result-row')

    for (const header of ['Insider', 'Shares', 'Issuer', 'Filing Date']) {
      expect(screen.getByRole('columnheader', { name: header })).toBeInTheDocument()
    }
  })

  it('combines symbol, name, and date range into the query string', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ results: [], page: 1, total_count: 0, has_next: false }))
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
      vi.fn().mockResolvedValue(jsonResponse({ error: 'No Insider Data Found: Real Stock?' })),
    )
    render(<InsiderData />)

    fillAndSearch({ symbol: 'ZZZZZ' })

    expect(await screen.findByText('No Insider Data Found: Real Stock?')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows a friendly message when the search succeeds with no matches', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ results: [], page: 1, total_count: 0, has_next: false })),
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

  it('shows a searching indicator and disables Search while the request is in flight', async () => {
    let resolveFetch
    const pending = new Promise((resolve) => {
      resolveFetch = resolve
    })
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(pending))
    render(<InsiderData />)

    fillAndSearch({ symbol: 'AAPL' })

    expect(await screen.findByText('Searching…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /search/i })).toBeDisabled()

    resolveFetch(jsonResponse({ results: [], page: 1, total_count: 0, has_next: false }))

    expect(await screen.findByText('No matching insider filings found.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /search/i })).toBeEnabled()
  })

  it('shows the Showing X-Y of Z range for the current page', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          results: [{ insider_name: 'Jane Doe', net_change: 100, issuer: 'AAPL', filing_date: '2026-08-10' }],
          page: 1,
          total_count: 15,
          has_next: true,
        }),
      ),
    )
    render(<InsiderData />)

    fillAndSearch({ symbol: 'AAPL' })

    expect(await screen.findByText('Showing 1–1 of 15')).toBeInTheDocument()
  })

  it('disables Previous on the first page and enables Next when has_next is true', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          results: [{ insider_name: 'Jane Doe', net_change: 100, issuer: 'AAPL', filing_date: '2026-08-10' }],
          page: 1,
          total_count: 15,
          has_next: true,
        }),
      ),
    )
    render(<InsiderData />)

    fillAndSearch({ symbol: 'AAPL' })
    await screen.findByTestId('insider-result-row')

    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled()
  })

  it('disables Next when has_next is false', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          results: [{ insider_name: 'Jane Doe', net_change: 100, issuer: 'AAPL', filing_date: '2026-08-10' }],
          page: 1,
          total_count: 1,
          has_next: false,
        }),
      ),
    )
    render(<InsiderData />)

    fillAndSearch({ symbol: 'AAPL' })
    await screen.findByTestId('insider-result-row')

    expect(screen.getByRole('button', { name: /^next$/i })).toBeDisabled()
  })

  it('advances to the next page and back, reusing the searched criteria', async () => {
    const page1 = {
      results: [{ insider_name: 'Jane Doe', net_change: 100, issuer: 'AAPL', filing_date: '2026-08-10' }],
      page: 1,
      total_count: 15,
      has_next: true,
    }
    const page2 = {
      results: [{ insider_name: 'John Smith', net_change: 200, issuer: 'AAPL', filing_date: '2026-08-01' }],
      page: 2,
      total_count: 15,
      has_next: false,
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(page1))
      .mockResolvedValueOnce(jsonResponse(page2))
      .mockResolvedValueOnce(jsonResponse(page1))
    vi.stubGlobal('fetch', fetchMock)
    render(<InsiderData />)

    fillAndSearch({ symbol: 'AAPL' })
    expect(await screen.findByText('Jane Doe')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^next$/i }))
    expect(await screen.findByText('John Smith')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenLastCalledWith('/api/insider-data?symbol=AAPL&page=2')
    expect(screen.getByRole('button', { name: /previous/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /^next$/i })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: /previous/i }))
    expect(await screen.findByText('Jane Doe')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenLastCalledWith('/api/insider-data?symbol=AAPL')
  })

  it('pages using the criteria from the last search, not the current (edited) input values', async () => {
    const page1 = {
      results: [{ insider_name: 'Jane Doe', net_change: 100, issuer: 'AAPL', filing_date: '2026-08-10' }],
      page: 1,
      total_count: 15,
      has_next: true,
    }
    const page2 = {
      results: [{ insider_name: 'John Smith', net_change: 200, issuer: 'AAPL', filing_date: '2026-08-01' }],
      page: 2,
      total_count: 15,
      has_next: false,
    }
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(page1)).mockResolvedValueOnce(jsonResponse(page2))
    vi.stubGlobal('fetch', fetchMock)
    render(<InsiderData />)

    fillAndSearch({ symbol: 'AAPL' })
    await screen.findByText('Jane Doe')

    // Edit the symbol field without clicking Search again.
    fillField('txtInsiderSymbol', 'MSFT')
    fireEvent.click(screen.getByRole('button', { name: /^next$/i }))

    await screen.findByText('John Smith')
    expect(fetchMock).toHaveBeenLastCalledWith('/api/insider-data?symbol=AAPL&page=2')
  })

  it('keeps pagination controls visible and usable when a page comes back empty but has_next is true', async () => {
    // The backend applies the name filter per-page, so a page within range
    // can legitimately have zero matching rows while has_next is still
    // true. Previous/Next must stay reachable so the user isn't stranded.
    const emptyPageWithMore = { results: [], page: 1, total_count: 12, has_next: true }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(emptyPageWithMore)))
    render(<InsiderData />)

    fillAndSearch({ symbol: 'AAPL', name: 'nomatch' })

    expect(await screen.findByText('No matching insider filings found.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^next$/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled()
  })

  it('does not show pagination controls before any search or after a blank-criteria guard', () => {
    vi.stubGlobal('fetch', vi.fn())
    render(<InsiderData />)

    expect(screen.queryByRole('button', { name: /^next$/i })).not.toBeInTheDocument()

    fillAndSearch()

    expect(screen.queryByRole('button', { name: /^next$/i })).not.toBeInTheDocument()
  })

  it('does not show pagination controls after a backend error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ error: 'No Insider Data Found: Real Stock?' })))
    render(<InsiderData />)

    fillAndSearch({ symbol: 'ZZZZZ' })

    await screen.findByText('No Insider Data Found: Real Stock?')
    expect(screen.queryByRole('button', { name: /^next$/i })).not.toBeInTheDocument()
  })

  it('shows a plain total for a name-filtered search too, since the backend now counts true name matches', async () => {
    // SCRUM-19: name searches go through SEC's full-text search on the
    // backend, so total_count is a real match count -- no "of up to"
    // caveat needed any more.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          results: [{ insider_name: 'Jane Doe', net_change: 100, issuer: 'AAPL', filing_date: '2026-08-10' }],
          page: 1,
          total_count: 40,
          has_next: true,
        }),
      ),
    )
    render(<InsiderData />)

    fillAndSearch({ symbol: 'AAPL', name: 'Jane' })

    expect(await screen.findByText('Showing 1–1 of 40')).toBeInTheDocument()
  })

  it('shows a plain total when no name filter is active', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse({
          results: [{ insider_name: 'Jane Doe', net_change: 100, issuer: 'AAPL', filing_date: '2026-08-10' }],
          page: 1,
          total_count: 15,
          has_next: true,
        }),
      ),
    )
    render(<InsiderData />)

    fillAndSearch({ symbol: 'AAPL' })

    expect(await screen.findByText('Showing 1–1 of 15')).toBeInTheDocument()
  })

  it('uses the page_size the backend reports instead of assuming 10', async () => {
    const page1 = {
      results: Array.from({ length: 5 }, (_, i) => ({
        insider_name: `Insider ${i}`,
        net_change: i,
        issuer: 'AAPL',
        filing_date: '2026-08-10',
      })),
      page: 1,
      page_size: 5,
      total_count: 12,
      has_next: true,
    }
    const page2 = {
      results: [{ insider_name: 'Last', net_change: 99, issuer: 'AAPL', filing_date: '2026-08-01' }],
      page: 2,
      page_size: 5,
      total_count: 12,
      has_next: false,
    }
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(page1)).mockResolvedValueOnce(jsonResponse(page2))
    vi.stubGlobal('fetch', fetchMock)
    render(<InsiderData />)

    fillAndSearch({ symbol: 'AAPL' })
    expect(await screen.findByText('Showing 1–5 of 12')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^next$/i }))

    // With page_size correctly picked up as 5 (not hardcoded 10), page 2
    // starts at result 6, not 11.
    expect(await screen.findByText('Showing 6–6 of 12')).toBeInTheDocument()
  })
})
