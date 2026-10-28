import { defineConfig, devices } from '@playwright/test'

/**
 * Regenerates the homepage screenshots (`npm run screenshots`).
 *
 * Starts the API on a fresh SQLite database, seeds the fictional demo review from
 * `screenshots/demo-data.ts` and writes WebP images to `src/assets/screenshots/`.
 * Never reuses a running server, so the images only ever show demo data.
 */
export default defineConfig({
  testDir: './screenshots',
  testMatch: 'capture.spec.ts',
  workers: 1,
  reporter: 'list',
  timeout: 180_000,

  use: {
    baseURL: 'http://localhost:5173',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: [
    {
      // No API key: AI verdicts are seeded, so nothing may call a model
      command:
        'cd .. && rm -rf screenshots_demo.db .screenshots_pdfs && unset PREFECT_API_URL ANTHROPIC_API_KEY && SECRET_KEY=screenshots-secret-key-not-for-production DATABASE_URL=sqlite:///screenshots_demo.db PDF_STORAGE_PATH=.screenshots_pdfs BILLING_ENABLED=false uvicorn app.main:app --host 0.0.0.0 --port 8000',
      url: 'http://localhost:8000/ping',
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: 'npx vite --port 5173',
      url: 'http://localhost:5173',
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
})
