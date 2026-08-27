// Feature: Insider-Transaction Screener (epic SCRUM-29)
// Covers: Feature branch & screener page scaffolding (SCRUM-30)
// Full behavioral coverage lands in QA: E2E coverage (SCRUM-40).

import { expect, test } from '@playwright/test'

test.describe('Insider Screener', () => {
  test('is reachable from the nav and renders the shell with the disclaimer', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: /screener/i }).click()

    await expect(page.getByRole('heading', { name: 'Insider Screener' })).toBeVisible()
    await expect(page.locator('#lblScreenerDisclaimer')).toContainText(/not investment advice/i)
  })
})
