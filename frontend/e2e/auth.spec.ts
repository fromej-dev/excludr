import { test, expect } from './fixtures'

test.describe('Authentication Flow', () => {
  test('should redirect to login when not authenticated', async ({ page }) => {
    await page.goto('/')
    await page.waitForURL('/login')
    expect(page.url()).toContain('/login')
  })

  test('should register a new user and redirect to dashboard', async ({ page, api }) => {
    const uid = Math.random().toString(36).slice(2, 10)
    const email = `new_user_${uid}@test.com`
    const name = `New User ${uid}`
    const password = 'NewPass123!'

    await page.goto('/register')
    await page.locator('#name').fill(name)
    await page.locator('#email').fill(email)
    await page.locator('#password').fill(password)
    await page.locator('#confirm-password').fill(password)

    // Click submit and wait for loading state
    const submitButton = page.locator('button[type="submit"]')
    await submitButton.click()
    await expect(submitButton).toHaveText(/Creating account.../, { timeout: 5000 })

    // Should redirect to dashboard
    await page.waitForURL('/', { timeout: 10000 })
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible()
  })

  test('should show error for mismatched passwords on register', async ({ page }) => {
    const uid = Math.random().toString(36).slice(2, 10)

    await page.goto('/register')
    await page.locator('#name').fill(`Test User ${uid}`)
    await page.locator('#email').fill(`test_${uid}@test.com`)
    await page.locator('#password').fill('Password123!')
    await page.locator('#confirm-password').fill('DifferentPassword123!')

    await page.locator('button[type="submit"]').click()

    // Should show error message
    await expect(page.getByText(/password/i)).toBeVisible()
  })

  test('should login with valid credentials', async ({ page, api }) => {
    // Register user via API
    const user = await api.register()

    // Login via UI
    await page.goto('/login')
    await page.locator('#email').fill(user.email)
    await page.locator('#password').fill(user.password)

    const submitButton = page.locator('button[type="submit"]')
    await submitButton.click()
    await expect(submitButton).toHaveText(/Signing in.../, { timeout: 5000 })

    // Should redirect to dashboard
    await page.waitForURL('/', { timeout: 10000 })
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible()
  })

  test('should show error for invalid login credentials', async ({ page }) => {
    await page.goto('/login')
    await page.locator('#email').fill('nonexistent@test.com')
    await page.locator('#password').fill('WrongPassword123!')

    await page.locator('button[type="submit"]').click()

    // Should show error message
    await expect(page.locator('div').filter({ hasText: /invalid|incorrect|error/i }).first()).toBeVisible({ timeout: 5000 })
  })

  test('should navigate between login and register pages', async ({ page }) => {
    // Start at login
    await page.goto('/login')
    expect(page.url()).toContain('/login')

    // Click link to register
    await page.getByRole('link', { name: /register|sign up|create account/i }).click()
    await page.waitForURL('/register')
    expect(page.url()).toContain('/register')

    // Click link back to login
    await page.getByRole('link', { name: /login|sign in/i }).click()
    await page.waitForURL('/login')
    expect(page.url()).toContain('/login')
  })

  test('should persist auth across page reload', async ({ page, pageHelper, testUser }) => {
    // Login using helper
    await pageHelper.loginViaUI(testUser.email, testUser.password)

    // Verify we're at dashboard
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible()

    // Reload the page
    await page.reload()

    // Should still be authenticated and at dashboard
    await expect(page).toHaveURL('/')
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible()

    // Verify token exists in localStorage
    const token = await page.evaluate(() => localStorage.getItem('excludr_token'))
    expect(token).toBeTruthy()
  })

  test('should redirect to login after token is cleared', async ({ page, pageHelper, testUser }) => {
    // Login using helper
    await pageHelper.loginViaUI(testUser.email, testUser.password)

    // Verify we're authenticated
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible()

    // Clear localStorage (remove token)
    await page.evaluate(() => localStorage.clear())

    // Navigate to dashboard
    await page.goto('/')

    // Should redirect to login
    await page.waitForURL('/login', { timeout: 10000 })
    expect(page.url()).toContain('/login')
  })
})
