import { test, expect } from './fixtures'

test.describe('Home page', () => {
  test('is public and links to sign up and sign in', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL('/')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Full-text screening')
    await expect(page.getByRole('link', { name: 'Sign in' }).first()).toHaveAttribute('href', '/login')
    await expect(page.getByRole('link', { name: 'Start your first review' })).toHaveAttribute('href', '/register')
  })

  test('offers the app to signed-in users', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginViaUI(testUser.email, testUser.password)
    await page.goto('/')
    await page.getByTestId('home-open-app').click()
    await expect(page).toHaveURL('/dashboard')
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible()
  })
})
