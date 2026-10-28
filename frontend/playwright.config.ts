import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E test configuration for Excludr.
 *
 * Starts both the FastAPI backend and Vite frontend dev server,
 * then runs browser tests against the live application.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? 'github' : 'html',
  timeout: 30_000,

  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  /* Start both servers before running tests */
  webServer: [
    {
      // PREFECT_API_URL is unset on purpose: with no Prefect server running, imports use
      // Prefect's ephemeral in-process API instead of failing to reach localhost:4200.
      // No automatic full-text retrieval: it would call Unpaywall/PMC after every include
      // decision, and its websocket events would race the events tests inject themselves.
      command:
        'cd .. && unset PREFECT_API_URL && SECRET_KEY="${SECRET_KEY:-e2e-test-secret-key-not-for-production}" DATABASE_URL="${DATABASE_URL:-sqlite:///e2e_test.db}" FULLTEXT_AUTO_RETRIEVAL=false uvicorn app.main:app --host 0.0.0.0 --port 8000',
      url: 'http://localhost:8000/ping',
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      command: 'npx vite --port 5173',
      url: 'http://localhost:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
  ],
})
