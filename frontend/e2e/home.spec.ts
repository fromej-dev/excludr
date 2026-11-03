import { test, expect } from './fixtures'

test.describe('Home page', () => {
  test('is public and links to sign up and sign in', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL('/')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Full-text screening')
    await expect(page.getByRole('link', { name: 'Sign in' }).first()).toHaveAttribute('href', '/login')
    await expect(page.getByRole('link', { name: 'Start your first review' })).toHaveAttribute('href', '/register')
  })

  test('shows the product screenshots', async ({ page }) => {
    await page.goto('/')
    const shots = page.getByTestId('home-screenshot')
    await expect(shots).toHaveCount(5)
    for (const shot of await shots.all()) {
      await shot.scrollIntoViewIfNeeded()
      await expect(shot).toHaveAttribute('alt', /\w/)
      await expect.poll(() => shot.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0)
    }
  })

  test('links to the prioritized screening explainer', async ({ page }) => {
    await page.goto('/')
    const link = page.getByRole('link', { name: /How the stopping rules work/ })
    await link.scrollIntoViewIfNeeded()
    await link.click()
    await expect(page).toHaveURL('/prioritized-screening')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Prioritized screening and stopping rules')
    // A new page opens at the top, not at the homepage's scroll position
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
    await expect(page.getByRole('link', { name: /doi\.org\/10\.1186\/s13643-020-01521-4/ })).toBeVisible()
  })

  test('offers the app to signed-in users', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginViaUI(testUser.email, testUser.password)
    await page.goto('/')
    await page.getByTestId('home-open-app').click()
    await expect(page).toHaveURL('/dashboard')
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible()
  })
})
