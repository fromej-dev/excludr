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
    await expect(shots).toHaveCount(4)
    for (const shot of await shots.all()) {
      await shot.scrollIntoViewIfNeeded()
      await expect(shot).toHaveAttribute('alt', /\w/)
      await expect.poll(() => shot.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0)
    }
  })

  test('offers the app to signed-in users', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginViaUI(testUser.email, testUser.password)
    await page.goto('/')
    await page.getByTestId('home-open-app').click()
    await expect(page).toHaveURL('/dashboard')
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible()
  })
})
