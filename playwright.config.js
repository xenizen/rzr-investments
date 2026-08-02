import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5183',
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: '.venv/bin/flask run --port 5001',
      cwd: 'backend',
      env: { FLASK_APP: 'app.py' },
      url: 'http://localhost:5001/api/stock-price?symbol=',
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
    {
      command: 'npm run dev -- --port 5183',
      url: 'http://localhost:5183',
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
    },
  ],
})
