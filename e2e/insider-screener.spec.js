// Feature: Insider-Transaction Screener (epic SCRUM-29)
// Covers: page scaffold (SCRUM-30), screener API endpoint (SCRUM-35),
// no-match / error handling (SCRUM-36), parameter form (SCRUM-37),
// results table + badge + states (SCRUM-38), pagination (SCRUM-39),
// months window + freshness copy (SCRUM-47).
//
// The whole backend pipeline (DB -> aggregate -> Alpaca -> rank -> paginate)
// is exercised by the pytest suite. Here the /api/insider-screener response
// is stubbed at the network boundary so the FE behaviour is deterministic
// and needs no seeded Postgres / Alpaca creds -- same approach as
// insider-data.spec.js.

import { expect, test } from '@playwright/test'

const API = '**/api/insider-screener**'

function makeRow(over = {}) {
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

function envelope(rows, { page = 1, total_count = rows.length, data_through = '2026-06-30' } = {}) {
  return {
    results: rows,
    page,
    page_size: 10,
    total_count,
    total_pages: Math.max(1, Math.ceil(total_count / 10)),
    has_next: page * 10 < total_count,
    data_through,
  }
}

function rowsFor(prefix, n) {
  return Array.from({ length: n }, (_, i) =>
    makeRow({ ticker: `${prefix}${i}`, company: `${prefix} Co ${i}`, multiple_insiders: false }),
  )
}

async function gotoScreener(page) {
  await page.goto('/')
  await page.getByRole('button', { name: /^screener$/i }).click()
  await expect(page.locator('#selScreenerDirection')).toBeVisible()
}

const runScreen = (page) => page.getByRole('button', { name: /run screen/i }).click()

test.describe('Insider Screener', () => {
  test('is reachable from the nav with the four dropdowns, disclaimer and freshness note', async ({ page }) => {
    await gotoScreener(page)

    await expect(page.getByRole('heading', { name: 'Insider Screener' })).toBeVisible()
    for (const id of ['selScreenerDirection', 'selScreenerShares', 'selScreenerMonths', 'selScreenerPct']) {
      await expect(page.locator(`#${id}`)).toBeVisible()
    }
    await expect(page.locator('#lblScreenerDisclaimer')).toContainText(/not investment advice/i)
    await expect(page.locator('#lblScreenerFreshness')).toContainText(/nightly/i)
  })

  test('the default run requests Purchase / 10000 / 1 month / 70% with no page param', async ({ page }) => {
    let requested
    await page.route(API, async (route) => {
      requested = new URL(route.request().url())
      await route.fulfill({ json: envelope([]) })
    })

    await gotoScreener(page)
    await runScreen(page)
    await expect(page.locator('#lblScreenerEmpty')).toBeVisible()

    expect(requested.searchParams.get('direction')).toBe('Purchase')
    expect(requested.searchParams.get('shares')).toBe('10000')
    expect(requested.searchParams.get('months')).toBe('1')
    expect(requested.searchParams.get('pct_below_high')).toBe('70')
    expect(requested.searchParams.has('page')).toBe(false)
  })

  test('changing every dropdown carries the new params into the request', async ({ page }) => {
    let requested
    await page.route(API, async (route) => {
      requested = new URL(route.request().url())
      await route.fulfill({ json: envelope([]) })
    })

    await gotoScreener(page)
    await page.locator('#selScreenerDirection').selectOption('Sold')
    await page.locator('#selScreenerShares').selectOption('20000')
    await page.locator('#selScreenerMonths').selectOption('4')
    await page.locator('#selScreenerPct').selectOption('90')
    await runScreen(page)
    await expect(page.locator('#lblScreenerEmpty')).toBeVisible()

    expect(requested.searchParams.get('direction')).toBe('Sold')
    expect(requested.searchParams.get('shares')).toBe('20000')
    expect(requested.searchParams.get('months')).toBe('4')
    expect(requested.searchParams.get('pct_below_high')).toBe('90')
  })

  test('renders a ranked table; multi-insider row carries the badge, single row does not', async ({ page }) => {
    const single = makeRow({ ticker: 'SNES', company: 'SenesTech, Inc.', side: 'buy', insider_count: 1, multiple_insiders: false })
    await page.route(API, (route) => route.fulfill({ json: envelope([makeRow(), single]) }))

    await gotoScreener(page)
    await runScreen(page)

    await expect(page.locator('#screenerResultsTable')).toBeVisible()
    await expect(page.locator('#lblScreenerRange')).toHaveText('Showing 1–2 of 2')

    const rows = page.getByTestId('screener-result-row')
    await expect(rows).toHaveCount(2)
    await expect(rows.nth(0)).toContainText('TRDA')
    await expect(rows.nth(0).getByText(/multi-insider/i)).toBeVisible()
    await expect(rows.nth(1)).toContainText('SNES')
    await expect(rows.nth(1).getByText(/multi-insider/i)).toHaveCount(0)
  })

  test('the review-window label reflects the selected months', async ({ page }) => {
    await page.route(API, (route) => route.fulfill({ json: envelope([makeRow()]) }))

    await gotoScreener(page)
    await page.locator('#selScreenerMonths').selectOption('3')
    await runScreen(page)

    await expect(page.locator('#lblScreenerWindow')).toHaveText('Reviewing insider filings from the last 3 months.')
  })

  test('the freshness note shows the data-through date after a screen', async ({ page }) => {
    await page.route(API, (route) => route.fulfill({ json: envelope([makeRow()], { data_through: '2026-06-30' }) }))

    await gotoScreener(page)
    await runScreen(page)

    await expect(page.locator('#lblScreenerFreshness')).toContainText('Insider data current through Jun 30, 2026')
  })

  test('clicking a ticker reveals its contributing filings', async ({ page }) => {
    await page.route(API, (route) => route.fulfill({ json: envelope([makeRow()]) }))

    await gotoScreener(page)
    await runScreen(page)
    await expect(page.getByTestId('screener-filings')).toHaveCount(0)

    await page.getByRole('button', { name: /TRDA/ }).click()
    const filings = page.getByTestId('screener-filings')
    await expect(filings).toContainText('A Person')
    await expect(filings).toContainText('B Person')
  })

  test('pages with Next/Previous, 10 per page, Next disables on the last page, re-run resets to page 1', async ({ page }) => {
    const p1 = envelope(rowsFor('P1_', 10), { page: 1, total_count: 23 })
    const p2 = envelope(rowsFor('P2_', 10), { page: 2, total_count: 23 })
    const p3 = envelope(rowsFor('P3_', 3), { page: 3, total_count: 23 })
    const fresh = envelope(rowsFor('NEW_', 4), { page: 1, total_count: 4 })

    await page.route(API, async (route) => {
      const url = new URL(route.request().url())
      const p = url.searchParams.get('page')
      if (url.searchParams.get('months') === '6') return route.fulfill({ json: fresh })
      return route.fulfill({ json: p === '3' ? p3 : p === '2' ? p2 : p1 })
    })

    await gotoScreener(page)
    await runScreen(page)

    await expect(page.locator('#lblScreenerRange')).toHaveText('Showing 1–10 of 23')
    await expect(page.getByTestId('screener-result-row')).toHaveCount(10)
    await expect(page.locator('#btnScreenerPrev')).toBeDisabled()

    await page.locator('#btnScreenerNext').click()
    await expect(page.locator('#lblScreenerRange')).toHaveText('Showing 11–20 of 23')
    await expect(page.getByText('P2_0')).toBeVisible()
    await expect(page.locator('.insider-page-info')).toHaveText('Page 2 of 3')
    await expect(page.locator('#btnScreenerPrev')).toBeEnabled()

    await page.locator('#btnScreenerNext').click()
    await expect(page.locator('#lblScreenerRange')).toHaveText('Showing 21–23 of 23')
    await expect(page.locator('#btnScreenerNext')).toBeDisabled()

    await page.locator('#btnScreenerPrev').click()
    await expect(page.locator('#lblScreenerRange')).toHaveText('Showing 11–20 of 23')

    // Re-running (with a changed dropdown) goes back to page 1.
    await page.locator('#selScreenerMonths').selectOption('6')
    await runScreen(page)
    await expect(page.locator('#lblScreenerRange')).toHaveText('Showing 1–4 of 4')
    await expect(page.locator('.insider-page-info')).toHaveText('Page 1 of 1')
  })

  test('a zero-result screen shows the empty state and no table', async ({ page }) => {
    await page.route(API, (route) => route.fulfill({ json: envelope([]) }))

    await gotoScreener(page)
    await runScreen(page)

    await expect(page.locator('#lblScreenerEmpty')).toContainText(/no matches for these parameters/i)
    await expect(page.locator('#screenerResultsTable')).toHaveCount(0)
    await expect(page.locator('#btnScreenerNext')).toHaveCount(0)
  })

  test('a backend error shows the friendly message as an alert, no table', async ({ page }) => {
    await page.route(API, (route) =>
      route.fulfill({
        status: 503,
        json: { error: 'The screener is temporarily unavailable. Please try again in a moment.' },
      }),
    )

    await gotoScreener(page)
    await runScreen(page)

    const alert = page.locator('#lblScreenerError')
    await expect(alert).toHaveAttribute('role', 'alert')
    await expect(alert).toContainText(/temporarily unavailable/i)
    await expect(page.locator('#lblScreenerEmpty')).toHaveCount(0)
    await expect(page.locator('#screenerResultsTable')).toHaveCount(0)
  })

  test('an Alpaca rate-limit error surfaces its own friendly message', async ({ page }) => {
    await page.route(API, (route) =>
      route.fulfill({
        status: 503,
        json: { error: 'Market price data is rate-limited right now. Please try again in a minute.' },
      }),
    )

    await gotoScreener(page)
    await runScreen(page)

    await expect(page.locator('#lblScreenerError')).toContainText(/rate-limited/i)
  })

  test('a failed request shows a fallback message', async ({ page }) => {
    await page.route(API, (route) => route.abort('failed'))

    await gotoScreener(page)
    await runScreen(page)

    await expect(page.locator('#lblScreenerError')).toContainText(/something went wrong running the screen/i)
  })

  test('the disclaimer stays visible after a screen runs', async ({ page }) => {
    await page.route(API, (route) => route.fulfill({ json: envelope([makeRow()]) }))

    await gotoScreener(page)
    await expect(page.locator('#lblScreenerDisclaimer')).toBeVisible()
    await runScreen(page)
    await expect(page.locator('#screenerResultsTable')).toBeVisible()
    await expect(page.locator('#lblScreenerDisclaimer')).toContainText(/not investment advice/i)
  })
})
