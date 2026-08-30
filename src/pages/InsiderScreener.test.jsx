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

function mockScreen(body) {
  const fetchMock = vi.fn().mockResolvedValue(jsonResponse(body))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const ROW = {
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
}

const SINGLE = {
  ticker: 'SNES',
  company: 'SenesTech, Inc.',
  side: 'buy',
  insider_count: 1,
  multiple_insiders: false,
  insiders: ['C Person'],
  total_insider_shares: 5172,
  current_price: 1.09,
  fifty_two_week_high: 5.35,
  discount_pct: 79.5,
  suggested_quantity: 10000,
  filings: [
    { accession_no: 'y-1', filing_date: '2026-06-29', transaction_date: '2026-06-29', insider_name: 'C Person', shares: 5172, price: 1.52 },
  ],
}

describe('InsiderScreener form', () => {
  it('renders the four dropdowns with the expected options and defaults', () => {
    render(<InsiderScreener />)

    const direction = document.getElementById('selScreenerDirection')
    expect([...direction.options].map((o) => o.value)).toEqual(['Purchase', 'Sold'])
    expect(direction.value).toBe('Purchase')
    expect(document.getElementById('selScreenerShares').value).toBe('10000')
    expect([...document.getElementById('selScreenerMonths').options].map((o) => o.value)).toEqual(
      ['1', '2', '3', '4', '5', '6'],
    )
    expect(document.getElementById('selScreenerMonths').value).toBe('1')
    expect(document.getElementById('selScreenerPct').value).toBe('70')
  })

  it('does not call the backend on mount', () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
    render(<InsiderScreener />)
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('fires one request with the selected parameters', async () => {
    const fetchMock = mockScreen({ results: [], total_count: 0, page: 1, has_next: false })
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
  })

  it('shows a screening indicator and disables the button while in flight', async () => {
    let resolveFetch
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise((resolve) => { resolveFetch = resolve })))
    render(<InsiderScreener />)

    runScreen()

    expect(await screen.findByText('Screening…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run screen/i })).toBeDisabled()

    resolveFetch(jsonResponse({ results: [], total_count: 0, page: 1, has_next: false }))
    expect(await screen.findByText(/no matches/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /run screen/i })).toBeEnabled()
  })
})

describe('InsiderScreener results', () => {
  it('renders every column from the row contract', async () => {
    mockScreen({ results: [ROW], total_count: 1, page: 1, has_next: false })
    render(<InsiderScreener />)
    runScreen()

    expect(await screen.findByText('1 match')).toBeInTheDocument()
    for (const header of ['Stock', 'Side', 'Insiders', 'Insider shares', 'Price', '52-wk high', '% below', 'Suggested qty']) {
      expect(screen.getByRole('columnheader', { name: header })).toBeInTheDocument()
    }

    const row = screen.getByTestId('screener-result-row')
    const cells = within(row).getAllByRole('cell')
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
    mockScreen({ results: [ROW, SINGLE], total_count: 2, page: 1, has_next: false })
    render(<InsiderScreener />)
    runScreen()

    await screen.findByText('2 matches')
    const [multi, single] = screen.getAllByTestId('screener-result-row')
    expect(within(multi).getByText(/multi-insider/i)).toBeInTheDocument()
    expect(within(single).queryByText(/multi-insider/i)).not.toBeInTheDocument()
  })

  it('expands a row to show its contributing filings, and collapses it again', async () => {
    mockScreen({ results: [ROW], total_count: 1, page: 1, has_next: false })
    render(<InsiderScreener />)
    runScreen()

    const toggle = await screen.findByRole('button', { name: /TRDA/ })
    expect(screen.queryByTestId('screener-filings')).not.toBeInTheDocument()

    fireEvent.click(toggle)
    const filings = screen.getByTestId('screener-filings')
    expect(within(filings).getByText('A Person')).toBeInTheDocument()
    expect(within(filings).getByText('B Person')).toBeInTheDocument()
    expect(toggle).toHaveAttribute('aria-expanded', 'true')

    fireEvent.click(toggle)
    expect(screen.queryByTestId('screener-filings')).not.toBeInTheDocument()
  })

  it('shows a distinct empty state on a successful zero-result screen', async () => {
    mockScreen({ results: [], total_count: 0, page: 1, has_next: false })
    render(<InsiderScreener />)
    runScreen()

    const empty = await screen.findByText(/no matches for these parameters/i)
    expect(empty).toHaveAttribute('id', 'lblScreenerEmpty')
    expect(empty).not.toHaveAttribute('role', 'alert')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('shows the backend error message as an alert, distinct from the empty state', async () => {
    mockScreen({ error: 'The screener is temporarily unavailable. Please try again in a moment.' })
    render(<InsiderScreener />)
    runScreen()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveAttribute('id', 'lblScreenerError')
    expect(alert).toHaveTextContent('temporarily unavailable')
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
    mockScreen({ results: [ROW], total_count: 1, page: 1, has_next: false })
    render(<InsiderScreener />)
    expect(screen.getByText(/not investment advice/i)).toBeInTheDocument()

    runScreen()
    await screen.findByText('1 match')
    expect(screen.getByText(/not investment advice/i)).toBeInTheDocument()
  })

  it('collapses an expanded row when a new screen is run', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ results: [ROW], total_count: 1, page: 1, has_next: false }))
      .mockResolvedValueOnce(jsonResponse({ results: [SINGLE], total_count: 1, page: 1, has_next: false }))
    vi.stubGlobal('fetch', fetchMock)
    render(<InsiderScreener />)

    runScreen()
    fireEvent.click(await screen.findByRole('button', { name: /TRDA/ }))
    expect(screen.getByTestId('screener-filings')).toBeInTheDocument()

    runScreen()
    await screen.findByRole('button', { name: /SNES/ })
    expect(screen.queryByTestId('screener-filings')).not.toBeInTheDocument()
  })
})
