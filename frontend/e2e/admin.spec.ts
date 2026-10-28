import { test, expect } from './fixtures'

test.describe('Admin area', () => {
  test('is hidden from regular users', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginViaUI(testUser.email, testUser.password)
    await expect(page.getByTestId('admin-link')).toHaveCount(0)
    await page.goto('/admin')
    await expect(page).toHaveURL('/dashboard')
  })

  test('admin manages plans and users', async ({ page, api, pageHelper }) => {
    const admin = await api.register()
    api.makeAdmin(admin.email)
    const owner = await api.register()
    const project = await api.createProject(owner.token)

    await pageHelper.loginViaUI(admin.email, admin.password)
    await page.getByTestId('admin-link').click()
    await expect(page.getByTestId('admin-overview')).toBeVisible()

    // Grant a pass, then extend it
    const adminNav = page.getByRole('navigation', { name: 'Admin sections' })
    await adminNav.getByRole('link', { name: 'Projects' }).click()
    await page.getByPlaceholder('Search by project or owner e-mail').fill(owner.email)
    const row = page.getByTestId('admin-project-row').filter({ hasText: project.name })
    await expect(row).toContainText('Free')
    await page.getByTestId(`manage-${project.id}`).click()
    await page.getByTestId('grant-pass').click()
    await expect(row).toContainText('Active')
    await expect(row).toContainText('pass_250')

    await page.getByTestId(`manage-${project.id}`).click()
    await page.getByRole('button', { name: '+1 year' }).click()
    await page.getByTestId('save-plan').click()
    await expect(page.getByText('Pass updated')).toBeVisible()

    // Deactivate the owner from their user page
    await row.getByRole('link', { name: owner.email }).click()
    await expect(page.getByRole('heading', { name: owner.name })).toBeVisible()
    page.once('dialog', (dialog) => dialog.accept())
    await page.getByTestId('toggle-active').click()
    await expect(page.getByTestId('user-deactivated')).toBeVisible()

    const res = await page.request.get('/api/v1/users/me', {
      headers: { Authorization: `Bearer ${owner.token}` },
    })
    expect(res.status()).toBe(401)

    await adminNav.getByRole('link', { name: 'Payments' }).click()
    await expect(page.getByRole('table')).toBeVisible()
  })
})
