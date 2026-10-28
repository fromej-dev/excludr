import { test, expect } from './fixtures'

test.describe('Account page', () => {
  test('opens from the sidebar and shows the owned projects', async ({ page, api, pageHelper, testUser }) => {
    const project = await api.createProject(testUser.token)
    await pageHelper.loginDirect(testUser.token)

    await page.getByTestId('account-link').click()
    await page.waitForURL('/account')
    await expect(page.getByRole('heading', { name: 'Account' })).toBeVisible()
    await expect(page.getByTestId('account-email')).toHaveText(testUser.email)
    await expect(page.getByTestId('usage-projects')).toContainText(project.name)
  })

  test('renames the user', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)
    await page.goto('/account')

    await page.getByTestId('account-name').fill('Renamed Researcher')
    await page.getByTestId('save-name').click()
    await expect(page.getByTestId('account-link')).toContainText('Renamed Researcher')
  })

  test('changes the password, then signs in with it', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)
    await page.goto('/account')

    await page.locator('#account-current-password').fill(testUser.password)
    await page.locator('#account-new-password').fill('BrandNewPass1!')
    await page.locator('#account-confirm-password').fill('BrandNewPass1!')
    await page.getByTestId('save-password').click()
    await expect(page.locator('#account-current-password')).toHaveValue('')

    await page.getByTestId('logout').click()
    await pageHelper.loginViaUI(testUser.email, 'BrandNewPass1!')
  })

  test('rejects a wrong current password', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)
    await page.goto('/account')

    await page.locator('#account-current-password').fill('not-my-password')
    await page.locator('#account-new-password').fill('BrandNewPass1!')
    await page.locator('#account-confirm-password').fill('BrandNewPass1!')
    await page.getByTestId('save-password').click()
    await expect(page.getByTestId('account-password').getByRole('alert')).toHaveText(
      'Current password is incorrect'
    )
  })

  test('changes the email and stays signed in', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)
    await page.goto('/account')

    const newEmail = `changed_${Math.random().toString(36).slice(2, 10)}@test.com`
    await page.getByTestId('change-email').click()
    await page.locator('#account-new-email').fill(newEmail)
    await page.locator('#account-email-password').fill(testUser.password)
    await page.getByTestId('save-email').click()
    await expect(page.getByTestId('account-email')).toHaveText(newEmail)

    await page.reload()
    await expect(page.getByTestId('account-email')).toHaveText(newEmail)
  })
})
