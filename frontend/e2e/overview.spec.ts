import { test, expect, generateRisContent } from './fixtures'

test.describe('Project overview', () => {
  test('next step guides from criteria to import to screening', async ({ page, pageHelper, testUser, api }) => {
    const project = await api.createProject(testUser.token, { review_question: 'Does X improve Y?' })
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'overview')

    const title = page.getByTestId('next-step-title')
    await expect(title).toHaveText('Define your inclusion/exclusion criteria')
    await expect(page.getByTestId('review-question')).toContainText('Does X improve Y?')
    await expect(page.getByTestId('setup-checklist')).toBeVisible()

    await api.createCriterion(testUser.token, project.id, { type: 'inclusion', code: 'I1', description: 'RCTs' })
    await page.reload()
    await expect(title).toHaveText('Import articles')

    await api.uploadRisFile(testUser.token, project.id, generateRisContent(3))
    await api.startScreening(testUser.token, project.id)
    await page.reload()
    await expect(title).toHaveText('Screen 3 articles')
    await expect(page.getByTestId('next-step-action')).toHaveAttribute('href', /stage=title_abstract/)
    // Setup is complete, so the checklist is gone
    await expect(page.getByTestId('setup-checklist')).toHaveCount(0)
  })

  test('mobile pill nav shows a single Screening pill', async ({ page, pageHelper, testUser, api }) => {
    const project = await api.createProject(testUser.token)
    await page.setViewportSize({ width: 390, height: 844 })
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'overview')

    const pills = page.getByTestId('project-pills')
    await expect(pills.getByRole('link', { name: /^Screening/ })).toHaveCount(1)
    await expect(pills.getByRole('link', { name: /^Title\/abstract/ })).toHaveCount(0)
    await expect(pills.getByRole('link', { name: /^Full text/ })).toHaveCount(0)

    await pills.getByRole('link', { name: /^Screening/ }).click()
    await expect(page).toHaveURL(/\/screening\?stage=title_abstract/)
    await expect(pills.getByRole('link', { name: /^Screening/ })).toHaveAttribute('aria-current', 'page')
  })

  test('next step resolves when the conflicts request fails', async ({ page, pageHelper, testUser, api }) => {
    const project = await api.createProject(testUser.token)
    await api.createCriterion(testUser.token, project.id, { type: 'inclusion', code: 'I1', description: 'RCTs' })
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(3))
    await api.startScreening(testUser.token, project.id)
    await page.route(/\/screening\/conflicts/, (route) => route.fulfill({ status: 500, body: '{}' }))

    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'overview')
    // Unknown conflicts do not block the rule that does apply
    await expect(page.getByTestId('next-step-title')).toHaveText('Screen 3 articles')
  })

  test('next step shows a retryable fallback when its data cannot load', async ({ page, pageHelper, testUser, api }) => {
    const project = await api.createProject(testUser.token)
    await api.createCriterion(testUser.token, project.id, { type: 'inclusion', code: 'I1', description: 'RCTs' })
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(3))
    await api.startScreening(testUser.token, project.id)
    const failing = [/\/screening\/stats/, /\/screening\/conflicts/, /pending_for_me=true/]
    const fail = (route: import('@playwright/test').Route) => route.fulfill({ status: 500, body: '{}' })
    for (const re of failing) await page.route(re, fail)

    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'overview')
    await expect(page.getByTestId('next-step-title')).toHaveText("Couldn't load the next step")
    await expect(page.getByRole('status', { name: 'Loading next step' })).toHaveCount(0)

    for (const re of failing) await page.unroute(re, fail)
    await page.getByTestId('next-step-retry').click()
    await expect(page.getByTestId('next-step-title')).toHaveText('Screen 3 articles')
  })
})
