import { test, expect, generateRisContent } from './fixtures'

test.describe('Articles Management', () => {
  test('should show empty state when no articles', async ({ pageHelper, api, testUser, page }) => {
    await pageHelper.loginDirect(testUser.token)
    const project = await api.createProject(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'articles')

    // Assert empty state is visible
    await expect(page.getByText(/no articles found/i)).toBeVisible()
  })

  test('should display imported articles after RIS upload', async ({ pageHelper, api, testUser, page }) => {
    await pageHelper.loginDirect(testUser.token)
    const project = await api.createProject(testUser.token)

    // Upload 3 articles
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(3))

    await pageHelper.goToProjectTab(project.id, 'articles')

    // Wait for article cards to appear
    await page.waitForSelector('h3', { timeout: 10000 })

    // Assert 3 article cards are visible with titles
    const articleTitles = await page.locator('h3').all()
    expect(articleTitles.length).toBe(3)

    // Verify titles contain expected pattern
    const firstTitle = await articleTitles[0].textContent()
    expect(firstTitle).toContain('E2E Test Article')
  })

  test('should navigate to article detail', async ({ pageHelper, api, testUser, page }) => {
    await pageHelper.loginDirect(testUser.token)
    const project = await api.createProject(testUser.token)
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(3))

    await pageHelper.goToProjectTab(project.id, 'articles')
    await page.waitForSelector('h3', { timeout: 10000 })

    // Get the first article's title from the list
    const firstArticleTitle = await page.locator('h3').first().textContent()

    // Click the first article card
    await page.locator('article').first().click()

    // Assert article detail page shows title as h1
    await expect(page.locator('h1')).toBeVisible({ timeout: 5000 })
    const detailTitle = await page.locator('h1').textContent()
    expect(detailTitle).toBe(firstArticleTitle)

    // Assert detail page shows abstract section
    await expect(page.getByText(/abstract/i)).toBeVisible()
  })

  test('should navigate back from article detail', async ({ pageHelper, api, testUser, page }) => {
    await pageHelper.loginDirect(testUser.token)
    const project = await api.createProject(testUser.token)
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(3))

    await pageHelper.goToProjectTab(project.id, 'articles')
    await page.waitForSelector('h3', { timeout: 10000 })

    // Navigate to detail page
    await page.locator('article').first().click()
    await expect(page.locator('h1')).toBeVisible({ timeout: 5000 })

    // Click back button
    await page.getByRole('button', { name: /back/i }).click()

    // Assert back on articles list - check for article cards
    await expect(page.locator('h3').first()).toBeVisible({ timeout: 5000 })
    const articleCount = await page.locator('h3').count()
    expect(articleCount).toBe(3)
  })

  test('should filter articles by status', async ({ pageHelper, api, testUser, page }) => {
    await pageHelper.loginDirect(testUser.token)
    const project = await api.createProject(testUser.token)

    // Upload articles (they start with status "imported")
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(5))

    // Start screening to move all imported articles to "screening" status
    await api.startScreening(testUser.token, project.id)

    await pageHelper.goToProjectTab(project.id, 'articles')
    await page.waitForSelector('h3', { timeout: 10000 })

    // Get initial count
    const initialCount = await page.locator('h3').count()
    expect(initialCount).toBe(5)

    // Apply status filter - select "screening"
    const statusSelect = page.getByLabel(/status/i).or(page.locator('select').filter({ hasText: /status/i }))
    await statusSelect.selectOption('screening')

    // Wait for filtered results
    await page.waitForTimeout(1000)

    // Assert filtered results show fewer articles
    const filteredCount = await page.locator('h3').count()
    expect(filteredCount).toBeLessThan(initialCount)
  })

  test('should clear filters', async ({ pageHelper, api, testUser, page }) => {
    await pageHelper.loginDirect(testUser.token)
    const project = await api.createProject(testUser.token)
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(5))

    await pageHelper.goToProjectTab(project.id, 'articles')
    await page.waitForSelector('h3', { timeout: 10000 })

    // Get initial count
    const initialCount = await page.locator('h3').count()
    expect(initialCount).toBe(5)

    // Apply a filter (filter by "imported" status)
    const statusSelect = page.getByLabel(/status/i).or(page.locator('select').filter({ hasText: /status/i }))
    await statusSelect.selectOption('imported')
    await page.waitForTimeout(500)

    // Click "Clear Filters" button
    await page.getByRole('button', { name: /clear filters/i }).click()
    await page.waitForTimeout(500)

    // Assert all articles shown again
    const afterClearCount = await page.locator('h3').count()
    expect(afterClearCount).toBe(initialCount)
  })

  test('should display article metadata', async ({ pageHelper, api, testUser, page }) => {
    await pageHelper.loginDirect(testUser.token)
    const project = await api.createProject(testUser.token)
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(3))

    await pageHelper.goToProjectTab(project.id, 'articles')
    await page.waitForSelector('h3', { timeout: 10000 })

    // Get the first article card
    const firstArticle = page.locator('article').first()

    // Assert article card displays metadata
    // Check for authors (should show "et al." pattern or author names)
    const hasAuthors = await firstArticle.getByText(/et al\.|Author/i).count()

    // Check for year (4-digit number)
    const hasYear = await firstArticle.locator('text=/\\d{4}/').count()

    // Check for journal
    const hasJournal = await firstArticle.getByText(/journal/i).count()

    // At least one type of metadata should be visible
    const hasMetadata = hasAuthors > 0 || hasYear > 0 || hasJournal > 0
    expect(hasMetadata).toBeTruthy()

    // Assert status badge is visible
    await expect(firstArticle.getByText(/imported|screening|included|excluded/i).first()).toBeVisible()
  })
})
