import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Stocks from './Stocks'

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
})
