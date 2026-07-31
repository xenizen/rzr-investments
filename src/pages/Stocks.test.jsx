import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Stocks from './Stocks'

afterEach(() => {
  vi.unstubAllGlobals()
})

function clickGetPrice(symbol) {
  if (symbol !== undefined) {
    fireEvent.change(document.getElementById('txtStockSymbol'), { target: { value: symbol } })
  }
  fireEvent.click(screen.getByRole('button', { name: /get price/i }))
}

describe('Stocks', () => {
  it('renders the stock symbol text field', () => {
    render(<Stocks />)
    const field = document.getElementById('txtStockSymbol')
    expect(field).toBeInTheDocument()
    expect(field.tagName).toBe('INPUT')
    expect(field).toHaveAttribute('type', 'text')
  })

  it('renders the get price button', () => {
    render(<Stocks />)
    const button = screen.getByRole('button', { name: /get price/i })
    expect(button).toBeInTheDocument()
    expect(button).toHaveAttribute('id', 'btnGetPrice')
  })

  it('renders the found price label', () => {
    render(<Stocks />)
    const label = document.getElementById('lblFoundPrice')
    expect(label).toBeInTheDocument()
    expect(label.tagName).toBe('LABEL')
  })

  it('fetches the price for the entered symbol and shows it in the label', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ json: () => Promise.resolve({ price: 123.45 }) }),
    )
    render(<Stocks />)

    clickGetPrice('AAPL')

    expect(await screen.findByText('123.45')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith('/api/stock-price?symbol=AAPL')
  })

  it('shows the backend error message when there is no price', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ json: () => Promise.resolve({ error: 'No Price Found: Real Stock?' }) }),
    )
    render(<Stocks />)

    clickGetPrice('ZZZZZ')

    expect(await screen.findByText('No Price Found: Real Stock?')).toBeInTheDocument()
  })

  it('shows the backend error message when no symbol was entered', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ json: () => Promise.resolve({ error: 'No Stock Entered' }) }),
    )
    render(<Stocks />)

    clickGetPrice()

    expect(await screen.findByText('No Stock Entered')).toBeInTheDocument()
  })

  it('updates the label again on a second click', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ json: () => Promise.resolve({ price: 100 }) })
      .mockResolvedValueOnce({ json: () => Promise.resolve({ price: 200 }) })
    vi.stubGlobal('fetch', fetchMock)
    render(<Stocks />)

    clickGetPrice('AAPL')
    expect(await screen.findByText('100')).toBeInTheDocument()

    clickGetPrice('MSFT')
    expect(await screen.findByText('200')).toBeInTheDocument()
  })

  it('shows a fallback error message if the request itself fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network down')))
    render(<Stocks />)

    clickGetPrice('AAPL')

    expect(await screen.findByText('No Price Found: Real Stock?')).toBeInTheDocument()
  })
})
