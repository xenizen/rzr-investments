// Feature: Get Stock Price
// Covers: FE: Get Price of a Stock (Todoist 6h9fX4wQfGXW84Mm), BE: Get Price of a stock (Todoist 6h9fXFFPQfC67Wcm), FE: Wire Alpaca to get stock price (Todoist 6hCJ8QPpjPF4F7xF), FE: CSS Design (Todoist 6hCMP62PFGwCF3QF)

import { expect, test } from '@playwright/test'

test.describe('Get Stock Price', () => {
  test('renders the stock symbol field, get-price button, and price label', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('#txtStockSymbol')).toBeVisible()
    await expect(page.getByRole('button', { name: /get price/i })).toBeVisible()
    // Empty by design until a lookup runs, so it has no rendered size --
    // check it exists rather than toBeVisible(), which requires a non-zero box.
    await expect(page.locator('#lblFoundPrice')).toBeAttached()
  })

  test('shows "No Stock Entered" when the button is clicked with an empty field', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: /get price/i }).click()
    await expect(page.locator('#lblFoundPrice')).toHaveText('No Stock Entered')
  })

  test('clicking with a symbol updates the label with a price or the "no price found" error', async ({ page }) => {
    await page.goto('/')
    await page.locator('#txtStockSymbol').fill('AAPL')
    await page.getByRole('button', { name: /get price/i }).click()
    await expect(page.locator('#lblFoundPrice')).toHaveText(/^(\d+(\.\d+)?|No Price Found: Real Stock\?)$/)
  })

  test('updates the label again on a second click with a different symbol', async ({ page }) => {
    await page.goto('/')
    const symbolField = page.locator('#txtStockSymbol')
    const label = page.locator('#lblFoundPrice')
    const button = page.getByRole('button', { name: /get price/i })

    await symbolField.fill('AAPL')
    await button.click()
    await expect(label).toHaveText(/^(\d+(\.\d+)?|No Price Found: Real Stock\?)$/)

    await symbolField.fill('')
    await button.click()
    await expect(label).toHaveText('No Stock Entered')
  })

  test('strips leading spaces from the symbol before requesting a price', async ({ page }) => {
    let requestedUrl = null
    await page.route('**/api/stock-price**', async (route) => {
      requestedUrl = new URL(route.request().url())
      await route.fulfill({ json: { price: 123.45 } })
    })

    await page.goto('/')
    await page.locator('#txtStockSymbol').fill('   AAPL')
    await page.getByRole('button', { name: /get price/i }).click()

    await expect(page.locator('#lblFoundPrice')).toHaveText('123.45')
    expect(requestedUrl.searchParams.get('symbol')).toBe('AAPL')
  })
})
