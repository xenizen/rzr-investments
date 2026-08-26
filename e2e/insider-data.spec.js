// Feature: Insider Data
// Covers: BE: Insider search endpoint (SCRUM-11), BE: Extend filtering (SCRUM-12),
// BE: Pagination (SCRUM-13), BE: Empty-input and error handling (SCRUM-14),
// FE: Insider Data page -- inputs (SCRUM-15),
// FE: Wire results, pagination controls, and error display (SCRUM-16)

import { expect, test } from '@playwright/test'

async function gotoInsiderData(page) {
  await page.goto('/')
  await page.getByRole('button', { name: /insider data/i }).click()
  await expect(page.locator('#txtInsiderSymbol')).toBeVisible()
}

test.describe('Insider Data', () => {
  test('renders the symbol, name, date range inputs and the search button', async ({ page }) => {
    await gotoInsiderData(page)
    await expect(page.locator('#txtInsiderSymbol')).toBeVisible()
    await expect(page.locator('#txtInsiderName')).toBeVisible()
    await expect(page.locator('#txtInsiderDateFrom')).toBeVisible()
    await expect(page.locator('#txtInsiderDateTo')).toBeVisible()
    await expect(page.getByRole('button', { name: /^search$/i })).toBeVisible()
  })

  test('shows "No Search Criteria Entered" and makes no API call when everything is blank', async ({ page }) => {
    let called = false
    await page.route('**/api/insider-data**', async (route) => {
      called = true
      await route.continue()
    })

    await gotoInsiderData(page)
    await page.getByRole('button', { name: /^search$/i }).click()

    await expect(page.locator('#lblInsiderMessage')).toHaveText('No Search Criteria Entered')
    expect(called).toBe(false)
  })

  test('searching by symbol alone renders a table of results', async ({ page }) => {
    await page.route('**/api/insider-data**', async (route) => {
      await route.fulfill({
        json: {
          results: [
            { insider_name: 'Jane Doe', net_change: 1000, issuer: 'Bakkt, Inc. (BKKT)', filing_date: '2026-08-01' },
          ],
          page: 1,
          total_count: 1,
          has_next: false,
        },
      })
    })

    await gotoInsiderData(page)
    await page.locator('#txtInsiderSymbol').fill('BKKT')
    await page.getByRole('button', { name: /^search$/i }).click()

    await expect(page.locator('#insiderResultsTable')).toBeVisible()
    await expect(page.getByText('Jane Doe')).toBeVisible()
  })

  test('searching by name alone renders a table of results', async ({ page }) => {
    await page.route('**/api/insider-data**', async (route) => {
      await route.fulfill({
        json: {
          results: [{ insider_name: 'Jane Doe', net_change: 250, issuer: 'Acme Corp', filing_date: '2026-07-15' }],
          page: 1,
          total_count: 1,
          has_next: false,
        },
      })
    })

    await gotoInsiderData(page)
    await page.locator('#txtInsiderName').fill('Jane Doe')
    await page.getByRole('button', { name: /^search$/i }).click()

    await expect(page.locator('#insiderResultsTable')).toBeVisible()
    await expect(page.getByText('Jane Doe')).toBeVisible()
  })

  test('combining symbol, name, and date range sends every filter ANDed in one request', async ({ page }) => {
    let requestedUrl = null
    await page.route('**/api/insider-data**', async (route) => {
      requestedUrl = new URL(route.request().url())
      await route.fulfill({
        json: {
          results: [
            { insider_name: 'Jane Doe', net_change: 500, issuer: 'Bakkt, Inc. (BKKT)', filing_date: '2026-01-15' },
          ],
          page: 1,
          total_count: 1,
          has_next: false,
        },
      })
    })

    await gotoInsiderData(page)
    await page.locator('#txtInsiderSymbol').fill('BKKT')
    await page.locator('#txtInsiderName').fill('Jane')
    await page.locator('#txtInsiderDateFrom').fill('2026-01-01')
    await page.locator('#txtInsiderDateTo').fill('2026-02-01')
    await page.getByRole('button', { name: /^search$/i }).click()

    await expect(page.getByText('Jane Doe')).toBeVisible()
    expect(requestedUrl.searchParams.get('symbol')).toBe('BKKT')
    expect(requestedUrl.searchParams.get('name')).toBe('Jane')
    expect(requestedUrl.searchParams.get('date_from')).toBe('2026-01-01')
    expect(requestedUrl.searchParams.get('date_to')).toBe('2026-02-01')
  })

  test('paginates with Next/Previous and disables Next on the last page', async ({ page }) => {
    const page1 = {
      results: Array.from({ length: 10 }, (_, i) => ({
        insider_name: `Insider ${i}`,
        net_change: i,
        issuer: 'AAPL',
        filing_date: '2026-08-10',
      })),
      page: 1,
      total_count: 12,
      has_next: true,
    }
    const page2 = {
      results: [{ insider_name: 'Last Insider', net_change: 99, issuer: 'AAPL', filing_date: '2026-01-01' }],
      page: 2,
      total_count: 12,
      has_next: false,
    }

    await page.route('**/api/insider-data**', async (route) => {
      const url = new URL(route.request().url())
      await route.fulfill({ json: url.searchParams.get('page') === '2' ? page2 : page1 })
    })

    await gotoInsiderData(page)
    await page.locator('#txtInsiderSymbol').fill('AAPL')
    await page.getByRole('button', { name: /^search$/i }).click()

    await expect(page.getByText('Insider 0')).toBeVisible()
    const nextBtn = page.locator('#btnNextPage')
    const prevBtn = page.locator('#btnPrevPage')
    await expect(prevBtn).toBeDisabled()
    await expect(nextBtn).toBeEnabled()

    await nextBtn.click()

    await expect(page.getByText('Last Insider')).toBeVisible()
    await expect(page.getByText('Insider 0')).toHaveCount(0)
    await expect(nextBtn).toBeDisabled()
    await expect(prevBtn).toBeEnabled()
  })

  test('shows a friendly message when the backend returns an error', async ({ page }) => {
    await page.route('**/api/insider-data**', async (route) => {
      await route.fulfill({ json: { error: 'No Insider Data Found: Real Stock?' } })
    })

    await gotoInsiderData(page)
    await page.locator('#txtInsiderSymbol').fill('ZZZZZ')
    await page.getByRole('button', { name: /^search$/i }).click()

    await expect(page.locator('#lblInsiderMessage')).toHaveText('No Insider Data Found: Real Stock?')
    await expect(page.locator('#insiderResultsTable')).not.toBeAttached()
  })

  test('shows a friendly message when the request itself fails', async ({ page }) => {
    await page.route('**/api/insider-data**', async (route) => {
      await route.abort('failed')
    })

    await gotoInsiderData(page)
    await page.locator('#txtInsiderSymbol').fill('AAPL')
    await page.getByRole('button', { name: /^search$/i }).click()

    await expect(page.locator('#lblInsiderMessage')).toHaveText('No Insider Data Found: Real Stock?')
  })

  test('a real symbol search against the live backend finishes loading', async ({ page }) => {
    // Unlike the mocked cases above, this hits the real backend (and SEC
    // EDGAR) to prove the wiring works end to end -- mirrors
    // get-stock-price.spec.js's un-mocked "clicking with a symbol" test.
    // Real insider lookups fetch and parse several individual filings, so
    // this is given a generous timeout rather than asserting on exact
    // result content (live data changes).
    test.setTimeout(60_000)

    await gotoInsiderData(page)
    await page.locator('#txtInsiderSymbol').fill('AAPL')
    await page.getByRole('button', { name: /^search$/i }).click()

    await expect(page.getByRole('button', { name: /^search$/i })).toBeEnabled({ timeout: 50_000 })
    await expect(page.locator('#lblInsiderMessage')).not.toHaveText('Searching…')
  })
})
