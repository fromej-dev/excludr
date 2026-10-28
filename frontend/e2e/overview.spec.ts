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
    await page.reload()
    await expect(title).toHaveText('Screen 3 articles')
    await expect(page.getByTestId('next-step-action')).toHaveAttribute('href', /stage=title_abstract/)
    // Setup is complete, so the checklist is gone
    await expect(page.getByTestId('setup-checklist')).toHaveCount(0)
  })

  test('mobile project sections live in the menu drawer', async ({ page, pageHelper, testUser, api }) => {
    const project = await api.createProject(testUser.token)
    await page.setViewportSize({ width: 390, height: 844 })
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'overview')

    // No second navigation row above the page; the sections are in the drawer
    await expect(page.getByTestId('project-pills')).toHaveCount(0)
    await page.getByTestId('menu-button').click()
    const sections = page.getByTestId('app-sidebar').getByRole('navigation', { name: 'Project sections' })
    await sections.getByRole('link', { name: /^Title\/abstract/ }).click()
    await expect(page).toHaveURL(/\/screening\?stage=title_abstract/)
    await expect(page.getByTestId('app-sidebar')).not.toBeInViewport()
  })

  test('next step resolves when the conflicts request fails', async ({ page, pageHelper, testUser, api }) => {
    const project = await api.createProject(testUser.token)
    await api.createCriterion(testUser.token, project.id, { type: 'inclusion', code: 'I1', description: 'RCTs' })
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(3))
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

  test('articles imported through the Overview upload are ready for title/abstract screening', async ({
    page,
    pageHelper,
    testUser,
    api,
  }) => {
    const project = await api.createProject(testUser.token)
    await api.createCriterion(testUser.token, project.id, { type: 'inclusion', code: 'I1', description: 'RCTs' })
    // The real UI flow must never need an explicit start-screening call
    const startScreeningCalls: string[] = []
    page.on('request', (req) => {
      if (req.url().includes('/articles/start-screening')) startScreeningCalls.push(req.url())
    })

    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'overview')
    await expect(page.getByTestId('next-step-title')).toHaveText('Import articles')

    await page.getByTestId('ris-input').setInputFiles({
      name: 'ui_import.ris',
      mimeType: 'application/x-research-info-systems',
      buffer: Buffer.from(generateRisContent(3)),
    })
    await expect(page.getByTestId('import-result')).toBeVisible({ timeout: 15_000 })

    const sidebar = page.getByTestId('project-sidebar')
    await expect(sidebar.getByTestId('nav-count-title_abstract')).toHaveText('3')
    await expect(page.getByTestId('next-step-title')).toHaveText('Screen 3 articles')

    await sidebar.getByRole('link', { name: /^Title\/abstract/ }).click()
    await expect(page).toHaveURL(/stage=title_abstract/)
    await expect(page.getByTestId('article-title')).toContainText('E2E Test Article', { timeout: 10_000 })
    expect(startScreeningCalls).toEqual([])
  })

  test('owner can release articles left in "imported" from the next step', async ({
    page,
    pageHelper,
    testUser,
    api,
  }) => {
    const project = await api.createProject(testUser.token)
    await api.createCriterion(testUser.token, project.id, { type: 'inclusion', code: 'I1', description: 'RCTs' })
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(3))

    // Imports no longer leave articles in "imported", so simulate legacy data in the stats until the
    // owner releases them; the start-screening call itself goes to the real backend.
    let released = false
    page.on('request', (req) => {
      if (req.method() === 'POST' && req.url().includes('/articles/start-screening')) released = true
    })
    await page.route(/\/screening\/stats/, async (route) => {
      const res = await route.fetch()
      const body = await res.json()
      if (!released) body.imported_not_started = 2
      await route.fulfill({ response: res, json: body })
    })

    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'overview')
    const title = page.getByTestId('next-step-title')
    await expect(title).toHaveText('Start screening 2 imported articles')

    const startScreening = page.waitForResponse(
      (r) => r.request().method() === 'POST' && r.url().includes('/articles/start-screening')
    )
    await page.getByTestId('next-step-action').click()
    expect((await startScreening).ok()).toBeTruthy()
    await expect(title).toHaveText('Screen 3 articles')
    await expect(page.getByTestId('project-sidebar').getByTestId('nav-count-title_abstract')).toHaveText('3')
  })
})
