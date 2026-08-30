import { fireEvent, render, screen, within } from '@testing-library/react'
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

function row(over = {}) {
  return {
    ticker: 'TRDA',
    company: 'Entrada Therapeutics, Inc.',
    side: 'sell',
    insider_count: 2,
    multiple_insiders: true,
    insiders: ['A Person', 'B Person'],
    total_insider_shares: 313570,
    current_price: 7.28,
    fifty_two_week_high: 16.45,
    discount_pct: 55.7,
    suggested_quantity: 10000,
    filings: [
      { accession_no: 'x-1', filing_date: '2026-06-20', transaction_date: '2026-06-19', insider_name: 'A Person', shares: 200000, price: 7.5 },
      { accession_no: 'x-2', filing_date: '2026-06-18', transaction_date: '2026-06-17', insider_name: 'B Person', shares: 113570, price: 7.1 },
    ],
    ...over,
  }
}

// Response builder that fills in the pagination envelope from the rows.
function screenResponse(rows, { page = 1, total_count = rows.length } = {}) {
  return {
    results: rows,
    page,
    page_size: 10,
    total_count,
    total_pages: Math.max(1, Math.ceil(total_count / 10)),
    has_next: page * 10 < total_count,
  }
}

function rowsFor(prefix, n) {
  return Array.from({ length: n }, (_, i) => row({ ticker: `${prefix}${i}`, multiple_insiders: false }))
}

const SINGLE = row({
  ticker: 'SNES',
  company: 'SenesTech, Inc.',
  side: 'buy',
  insider_count: 1,
  multiple_insiders: false,
  filings: [{ accession_no: 'y-1', filing_date: '2026-06-29', transaction_date: '2026-06-29', insider_name: 'C Person', shares: 5172, price: 1.52 }],
})

describe('InsiderScreener form', () => {
  it('renders the four dropdowns with the expected options and defaults', () => {
    render(<InsiderScreener />)
    expect([...document.getElementById('selScreenerDirection').options].map((o) => o.value)).toEqual(['Purchase', 'Sold'])
    expect(document.getElementById('selScreenerShares').value).toBe('10000')
    expect([...document.getElementById('selScreenerMonths').options].map((o) => o.value)).toEqual(['1', '2', '3', '4', '5', '6'])
    expect(document.getElementById('selScreenerMonths').value).toBe('1')
    expect(document.getElementById('selScreenerPct').value).toBe('70')
  })

  it('does not call the backend on mount', () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
    render(<InsiderScreener />)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('fires one request with the selected parameters (no page param on page 1)', () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(screenResponse([])))
    vi.stubGlobal('fetch', fetchMock)
    render(<InsiderScreener />)

    fireEvent.change(document.getElementById('selScreenerDirection'), { target: { value: 'Sold' } })
    fireEvent.change(document.getElementById('selScreenerShares'), { target: { value: '15000' } })
    fireEvent.change(document.getElementById('selScreenerMonths'), { target: { value: '3' } })
    fireEvent.change(document.getElementById('selScreenerPct'), { target: { value: '80' } })
    runScreen()

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith('/api/insider-screener?direction=Sold&shares=15000&months=3&pct_below_high=80')
  })

  it('shows a screening indicator and disables the button while in flight', async () => {
    let resolveFetch
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise((resolve) => { resolveFetch = resolve })))
    render(<InsiderScreener />)

    runScreen()
    expect(await screen.findByText('Screening…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run screen/i })).toBeDisabled()

    resolveFetch(jsonResponse(screenResponse([])))
    expect(await screen.findByText(/no matches/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run screen/i })).toBeEnabled()
  })
})

describe('InsiderScreener results', () => {
  it('renders every column from the row contract', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(screenResponse([row()]))))
    render(<InsiderScreener />)
    runScreen()

    await screen.findByRole('table')
    for (const header of ['Stock', 'Side', 'Insiders', 'Insider shares', 'Price', '52-wk high', '% below', 'Suggested qty']) {
      expect(screen.getByRole('columnheader', { name: header })).toBeInTheDocument()
    }
    const cells = within(screen.getByTestId('screener-result-row')).getAllByRole('cell')
    expect(cells[0]).toHaveTextContent('TRDA')
    expect(cells[0]).toHaveTextContent('Entrada Therapeutics, Inc.')
    expect(cells[1]).toHaveTextContent('sell')
    expect(cells[2]).toHaveTextContent('2')
    expect(cells[3]).toHaveTextContent('313,570')
    expect(cells[4]).toHaveTextContent('$7.28')
    expect(cells[5]).toHaveTextContent('$16.45')
    expect(cells[6]).toHaveTextContent('55.7%')
    expect(cells[7]).toHaveTextContent('10,000')
  })

  it('shows the multi-insider badge only on flagged rows', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(screenResponse([row(), SINGLE]))))
    render(<InsiderScreener />)
    runScreen()

    await screen.findByRole('table')
    const [multi, single] = screen.getAllByTestId('screener-result-row')
    expect(within(multi).getByText(/multi-insider/i)).toBeInTheDocument()
    expect(within(single).queryByText(/multi-insider/i)).not.toBeInTheDocument()
  })

  it('expands a row to show its contributing filings, and collapses it again', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(screenResponse([row()]))))
    render(<InsiderScreener />)
    runScreen()

    const toggle = await screen.findByRole('button', { name: /TRDA/ })
    expect(screen.queryByTestId('screener-filings')).not.toBeInTheDocument()

    fireEvent.click(toggle)
    expect(within(screen.getByTestId('screener-filings')).getByText('A Person')).toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-expanded', 'true')

    fireEvent.click(toggle)
    expect(screen.queryByTestId('screener-filings')).not.toBeInTheDocument()
  })

  it('shows a distinct empty state on a successful zero-result screen', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(screenResponse([]))))
    render(<InsiderScreener />)
    runScreen()

    const empty = await screen.findByText(/no matches for these parameters/i)
    expect(empty).toHaveAttribute('id', 'lblScreenerEmpty')
    expect(empty).not.toHaveAttribute('role', 'alert')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /next/i })).not.toBeInTheDocument()
  })

  it('shows the backend error message as an alert, distinct from the empty state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ error: 'The screener is temporarily unavailable.' })))
    render(<InsiderScreener />)
    runScreen()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveAttribute('id', 'lblScreenerError')
    expect(screen.queryByText(/no matches/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows a fallback message when the request itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')))
    render(<InsiderScreener />)
    runScreen()
    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong running the screen')
  })

  it('keeps the disclaimer visible in every state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(screenResponse([row()]))))
    render(<InsiderScreener />)
    expect(screen.getByText(/not investment advice/i)).toBeInTheDocument()
    runScreen()
    await screen.findByRole('table')
    expect(screen.getByText(/not investment advice/i)).toBeInTheDocument()
  })
})

describe('InsiderScreener copy', () => {
  it('always shows the data-freshness note', () => {
    render(<InsiderScreener />)
    const note = document.getElementById('lblScreenerFreshness')
    expect(note).toHaveTextContent(/quarterly bulk Form 4 data/i)
    expect(note).toHaveTextContent(/topped up nightly from EDGAR/i)
  })

  it('names the review window once a screen has run, matching the selection', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(screenResponse([row()]))))
    render(<InsiderScreener />)

    // nothing before the first run
    expect(document.getElementById('lblScreenerWindow')).toBeNull()

    fireEvent.change(document.getElementById('selScreenerMonths'), { target: { value: '3' } })
    runScreen()

    await screen.findByRole('table')
    expect(document.getElementById('lblScreenerWindow')).toHaveTextContent(
      'Reviewing insider filings from the last 3 months.',
    )
  })

  it('names the review window on a zero-result screen too', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(screenResponse([]))))
    render(<InsiderScreener />)
    runScreen()

    await screen.findByText(/no matches for these parameters/i)
    expect(document.getElementById('lblScreenerWindow')).toHaveTextContent(
      'Reviewing insider filings from the last month.',
    )
  })
})

describe('InsiderScreener pagination', () => {
  it('shows no pagination controls before a screen is run', () => {
    render(<InsiderScreener />)
    expect(screen.queryByRole('button', { name: /^next$/i })).not.toBeInTheDocument()
  })

  it('shows the range indicator and disables both controls for a single page', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(screenResponse(rowsFor('A', 4)))))
    render(<InsiderScreener />)
    runScreen()

    expect(await screen.findByText('Showing 1–4 of 4')).toBeInTheDocument()
    expect(screen.getByText('Page 1 of 1')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /^next$/i })).toBeDisabled()
  })

  it('pages forward and back, requesting the right page each time', async () => {
    const page1 = screenResponse(rowsFor('P1_', 10), { page: 1, total_count: 23 })
    const page2 = screenResponse(rowsFor('P2_', 10), { page: 2, total_count: 23 })
    const page3 = screenResponse(rowsFor('P3_', 3), { page: 3, total_count: 23 })
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(page1))
      .mockResolvedValueOnce(jsonResponse(page2))
      .mockResolvedValueOnce(jsonResponse(page3))
      .mockResolvedValueOnce(jsonResponse(page2))
    vi.stubGlobal('fetch', fetchMock)
    render(<InsiderScreener />)

    runScreen()
    expect(await screen.findByText('Showing 1–10 of 23')).toBeInTheDocument()
    expect(screen.getByText('P1_0')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: /^next$/i }))
    expect(await screen.findByText('Showing 11–20 of 23')).toBeInTheDocument()
    expect(screen.getByText('P2_0')).toBeInTheDocument()
    expect(screen.queryByText('P1_0')).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/insider-screener?direction=Purchase&shares=10000&months=1&pct_below_high=70&page=2',
    )
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^next$/i }))
    expect(await screen.findByText('Showing 21–23 of 23')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^next$/i })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: /previous/i }))
    expect(await screen.findByText('Showing 11–20 of 23')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/insider-screener?direction=Purchase&shares=10000&months=1&pct_below_high=70&page=2',
    )
  })

  it('re-running resets to page 1, even after a dropdown change', async () => {
    const page1 = screenResponse(rowsFor('A', 10), { page: 1, total_count: 23 })
    const page2 = screenResponse(rowsFor('B', 10), { page: 2, total_count: 23 })
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(page1))
      .mockResolvedValueOnce(jsonResponse(page2))
      .mockResolvedValueOnce(jsonResponse(screenResponse(rowsFor('C', 2), { page: 1, total_count: 2 })))
    vi.stubGlobal('fetch', fetchMock)
    render(<InsiderScreener />)

    runScreen()
    await screen.findByText('Showing 1–10 of 23')
    fireEvent.click(screen.getByRole('button', { name: /^next$/i }))
    await screen.findByText('Showing 11–20 of 23')

    fireEvent.change(document.getElementById('selScreenerMonths'), { target: { value: '6' } })
    runScreen()

    await screen.findByText('Showing 1–2 of 2')
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/insider-screener?direction=Purchase&shares=10000&months=6&pct_below_high=70',
    )
    expect(screen.getByText('Page 1 of 1')).toBeInTheDocument()
  })

  it('pages using the params from the last run, not the current dropdown values', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(screenResponse(rowsFor('A', 10), { page: 1, total_count: 15 })))
      .mockResolvedValueOnce(jsonResponse(screenResponse(rowsFor('B', 5), { page: 2, total_count: 15 })))
    vi.stubGlobal('fetch', fetchMock)
    render(<InsiderScreener />)

    runScreen()
    await screen.findByText('Showing 1–10 of 15')

    // Change a dropdown without clicking Run screen.
    fireEvent.change(document.getElementById('selScreenerDirection'), { target: { value: 'Sold' } })
    fireEvent.click(screen.getByRole('button', { name: /^next$/i }))

    await screen.findByText('Showing 11–15 of 15')
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/insider-screener?direction=Purchase&shares=10000&months=1&pct_below_high=70&page=2',
    )
  })

  it('keeps the current results visible while the next page loads', async () => {
    let resolveNext
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(screenResponse(rowsFor('P1_', 10), { page: 1, total_count: 23 })))
      .mockReturnValueOnce(new Promise((resolve) => { resolveNext = resolve }))
    vi.stubGlobal('fetch', fetchMock)
    render(<InsiderScreener />)

    runScreen()
    await screen.findByText('Showing 1–10 of 23')

    fireEvent.click(screen.getByRole('button', { name: /^next$/i }))

    // Old rows still on screen, status switched to Screening…, controls locked.
    expect(screen.getByText('P1_0')).toBeInTheDocument()
    expect(screen.getByText('Screening…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^next$/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled()

    resolveNext(jsonResponse(screenResponse(rowsFor('P2_', 10), { page: 2, total_count: 23 })))
    expect(await screen.findByText('Showing 11–20 of 23')).toBeInTheDocument()
  })
})
