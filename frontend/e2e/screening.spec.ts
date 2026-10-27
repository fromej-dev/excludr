import { test, expect, generateRisContent } from './fixtures'

test.describe('Screening Workflow', () => {
  let projectId: number

  test.beforeEach(async ({ api, testUser }) => {
    // Create project with criteria and articles
    const project = await api.createProject(testUser.token, {
      name: 'Screening Test Project',
      description: 'Testing screening workflow',
      review_question: 'What is the effect of X on Y?',
    })
    projectId = project.id

    // Create inclusion criterion
    await api.createCriterion(testUser.token, projectId, {
      code: 'I1',
      description: 'Studies must be randomized controlled trials',
      rationale: 'RCTs provide strongest evidence',
      type: 'inclusion',
    })

    // Create exclusion criterion
    await api.createCriterion(testUser.token, projectId, {
      code: 'E1',
      description: 'Studies must not be animal studies',
      rationale: 'We are focusing on human subjects',
      type: 'exclusion',
    })

    // Upload articles (generates 5 articles in "imported" status)
    const risContent = generateRisContent(5)
    await api.uploadRisFile(testUser.token, projectId, risContent)

    // Start screening (moves articles from "imported" to "screening" status)
    await api.startScreening(testUser.token, projectId)
  })

  test('should display first article for screening', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'screening')

    // Wait for article to load
    await page.getByTestId('article-title').waitFor({ timeout: 10000 })

    // Assert article title visible
    const title = page.getByTestId('article-title').first()
    await expect(title).toBeVisible()
    const titleText = await title.textContent()
    expect(titleText).toContain('E2E Test Article')

    // Assert reasoning textarea visible
    const reasoning = page.locator('#reasoning')
    await expect(reasoning).toBeVisible()

    // Assert all three decision buttons visible
    const includeBtn = page.getByRole('button', { name: /include/i })
    const excludeBtn = page.getByRole('button', { name: /exclude/i })
    const uncertainBtn = page.getByRole('button', { name: /uncertain/i })

    await expect(includeBtn).toBeVisible()
    await expect(excludeBtn).toBeVisible()
    await expect(uncertainBtn).toBeVisible()
  })

  test('should show criteria reference panel', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'screening')

    await page.getByTestId('article-title').waitFor({ timeout: 10000 })

    // Check for inclusion criteria section
    const inclusionHeading = page.getByText('Inclusion Criteria')
    await expect(inclusionHeading).toBeVisible()

    // Check for specific inclusion criterion code and description
    const i1Code = page.getByText('I1', { exact: true })
    await expect(i1Code).toBeVisible()

    const i1Description = page.getByText('Studies must be randomized controlled trials')
    await expect(i1Description).toBeVisible()

    // Check for exclusion criteria section
    const exclusionHeading = page.getByText('Exclusion Criteria')
    await expect(exclusionHeading).toBeVisible()

    // Check for specific exclusion criterion code and description
    const e1Code = page.getByText('E1', { exact: true })
    await expect(e1Code).toBeVisible()

    const e1Description = page.getByText('Studies must not be animal studies')
    await expect(e1Description).toBeVisible()
  })

  test('should show screening stats', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'screening')

    await page.getByTestId('article-title').waitFor({ timeout: 10000 })

    // Toolbar shows progress for the current stage (nothing screened yet, 5 articles total)
    await expect(page.getByTestId('screening-progress')).toContainText('0 / 5 screened')
    await expect(page.getByText('Included', { exact: true })).toBeVisible()
    await expect(page.getByText('Excluded', { exact: true })).toBeVisible()
  })

  test('should use full-text screened count when on the full text stage', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)
    // Stats are mocked so the two stages report different counts
    await page.route('**/screening/stats', async (route) => {
      const res = await route.fetch()
      const body = await res.json()
      const data = { ...(body.data ?? body), screened_title_abstract: 2, screened_full_text: 4 }
      await route.fulfill({ response: res, json: body.data ? { ...body, data } : data })
    })
    await pageHelper.goToProjectTab(projectId, 'screening')
    await page.getByTestId('article-title').waitFor({ timeout: 10000 })

    await expect(page.getByTestId('screened-count')).toHaveText('2')
    await page.getByRole('tab', { name: 'Full text' }).click()
    await expect(page.getByRole('tab', { name: 'Full text' })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByTestId('screened-count')).toHaveText('4')
  })

  test('should undo the last decision via the toast', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'screening')
    await page.getByTestId('article-title').waitFor({ timeout: 10000 })

    const firstTitle = (await page.getByTestId('article-title').first().textContent())!.trim()
    await page.getByRole('button', { name: /include \(i\)/i }).click()

    const toast = page.getByRole('alert').filter({ hasText: 'Included:' })
    await expect(toast).toBeVisible()
    await expect(page.getByTestId('article-title')).not.toHaveText(firstTitle)

    await toast.getByRole('button', { name: 'Undo' }).click()

    await expect(page.getByTestId('article-title')).toHaveText(firstTitle)
    await expect(page.getByTestId('my-decision')).toContainText('Include')
    await expect(toast).toHaveCount(0)
  })

  test('should undo the last decision with the Z shortcut', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'screening')
    await page.getByTestId('article-title').waitFor({ timeout: 10000 })

    const firstTitle = (await page.getByTestId('article-title').first().textContent())!.trim()
    await page.keyboard.press('e')
    await expect(page.getByTestId('article-title')).not.toHaveText(firstTitle)

    await page.keyboard.press('z')
    await expect(page.getByTestId('article-title')).toHaveText(firstTitle)
    await expect(page.getByTestId('my-decision')).toContainText('Exclude')
  })

  test('should submit include decision and load next article', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'screening')

    await page.getByTestId('article-title').waitFor({ timeout: 10000 })

    // Get the first article title
    const firstTitle = await page.getByTestId('article-title').first().textContent()

    // Enter reasoning in textarea
    const reasoning = page.locator('#reasoning')
    await reasoning.fill('This article meets all inclusion criteria and is an RCT')

    // Click Include button
    const includeBtn = page.getByRole('button', { name: /include \(i\)/i })
    await includeBtn.click()

    // Wait for next article to load (title should change)
    await page.waitForTimeout(1000)

    // Assert next article loaded (different title)
    const secondTitle = await page.getByTestId('article-title').first().textContent()
    expect(secondTitle).not.toBe(firstTitle)
    expect(secondTitle).toContain('E2E Test Article')

    // Assert reasoning field is cleared for next article
    const reasoningValue = await reasoning.inputValue()
    expect(reasoningValue).toBe('')
  })

  test('should submit exclude decision', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'screening')

    await page.getByTestId('article-title').waitFor({ timeout: 10000 })

    const firstTitle = await page.getByTestId('article-title').first().textContent()

    // Enter reasoning
    const reasoning = page.locator('#reasoning')
    await reasoning.fill('This is an animal study')

    // Click Exclude button (destructive variant)
    const excludeBtn = page.getByRole('button', { name: /exclude \(e\)/i })
    await excludeBtn.click()

    // Wait for next article to load
    await page.waitForTimeout(1000)

    // Assert next article loaded
    const secondTitle = await page.getByTestId('article-title').first().textContent()
    expect(secondTitle).not.toBe(firstTitle)
  })

  test('should submit uncertain decision', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'screening')

    await page.getByTestId('article-title').waitFor({ timeout: 10000 })

    const firstTitle = await page.getByTestId('article-title').first().textContent()

    // Enter reasoning
    const reasoning = page.locator('#reasoning')
    await reasoning.fill('Need to review full text to decide')

    // Click Uncertain button (outline variant)
    const uncertainBtn = page.getByRole('button', { name: /uncertain \(u\)/i })
    await uncertainBtn.click()

    // Wait for next article to load
    await page.waitForTimeout(1000)

    // Assert next article loaded
    const secondTitle = await page.getByTestId('article-title').first().textContent()
    expect(secondTitle).not.toBe(firstTitle)
  })

  test('should use keyboard shortcut for include', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'screening')

    await page.getByTestId('article-title').waitFor({ timeout: 10000 })

    const firstTitle = await page.getByTestId('article-title').first().textContent()

    // Press 'i' key for include
    await page.keyboard.press('i')

    // Wait for next article to load
    await page.waitForTimeout(1000)

    // Assert next article loaded
    const secondTitle = await page.getByTestId('article-title').first().textContent()
    expect(secondTitle).not.toBe(firstTitle)

    // Verify keyboard shortcut hint is visible
    const shortcutHint = page.getByTestId('shortcut-legend').getByText(/use keyboard shortcuts/i)
    await expect(shortcutHint).toBeVisible()
  })

  test('should show no more articles when all screened', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'screening')

    await page.getByTestId('article-title').waitFor({ timeout: 10000 })

    // Screen all 5 articles using keyboard shortcut
    for (let i = 0; i < 5; i++) {
      await page.keyboard.press('i')
      await page.waitForTimeout(800) // Wait for article to load and process
    }

    // Wait a bit longer for the "no more articles" state to render
    await page.waitForTimeout(1000)

    // Assert "no more articles" message is visible
    const noMoreHeading = page.getByRole('heading', { name: /no more articles to screen/i })
    await expect(noMoreHeading).toBeVisible()

    const completionMessage = page.getByText(/you've completed screening all available articles/i)
    await expect(completionMessage).toBeVisible()
  })
})
