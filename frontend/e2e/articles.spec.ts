import type { Page } from '@playwright/test'
import { test, expect, generateRisContent } from './fixtures'

const articleCards = (page: Page) => page.getByTestId('article-card')
const articleTitles = (page: Page) => page.getByTestId('article-card-title')

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
    await articleCards(page).first().waitFor({ timeout: 10000 })

    // Assert 3 article cards are visible with titles
    const titles = await articleTitles(page).all()
    expect(titles.length).toBe(3)

    // Verify titles contain expected pattern
    const firstTitle = await titles[0].textContent()
    expect(firstTitle).toContain('E2E Test Article')
  })

  test('should navigate to article detail', async ({ pageHelper, api, testUser, page }) => {
    await pageHelper.loginDirect(testUser.token)
    const project = await api.createProject(testUser.token)
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(3))

    await pageHelper.goToProjectTab(project.id, 'articles')
    await articleCards(page).first().waitFor({ timeout: 10000 })

    // Get the first article's title from the list
    const firstArticleTitle = await articleTitles(page).first().textContent()

    // Click the first article card
    await articleCards(page).first().click()

    // Assert article detail page shows title as h1
    const detailHeading = page.getByTestId('article-detail-title')
    await expect(detailHeading).toBeVisible({ timeout: 5000 })
    expect((await detailHeading.textContent())?.trim()).toBe(firstArticleTitle?.trim())

    // Assert detail page shows abstract section
    await expect(page.getByRole('heading', { name: 'Abstract' })).toBeVisible()
  })

  test('should navigate back from article detail', async ({ pageHelper, api, testUser, page }) => {
    await pageHelper.loginDirect(testUser.token)
    const project = await api.createProject(testUser.token)
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(3))

    await pageHelper.goToProjectTab(project.id, 'articles')
    await articleCards(page).first().waitFor({ timeout: 10000 })

    // Navigate to detail page
    await articleCards(page).first().click()
    await expect(page.getByTestId('article-detail-title')).toBeVisible({ timeout: 5000 })

    // Click back button
    await page.getByRole('button', { name: /back/i }).click()

    // Assert back on articles list - check for article cards
    await expect(articleTitles(page).first()).toBeVisible({ timeout: 5000 })
    const articleCount = await articleTitles(page).count()
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
    await articleCards(page).first().waitFor({ timeout: 10000 })

    // Get initial count
    const initialCount = await articleTitles(page).count()
    expect(initialCount).toBe(5)

    const statusSelect = page.getByLabel('Status', { exact: true })

    // All 5 articles moved to "screening", so "imported" matches none
    await statusSelect.selectOption('imported')
    await expect(page.getByText(/no articles found/i)).toBeVisible()
    await expect(articleTitles(page)).toHaveCount(0)

    // ... and "screening" matches all of them
    await statusSelect.selectOption('screening')
    await expect(articleTitles(page)).toHaveCount(initialCount)
  })

  test('should clear filters', async ({ pageHelper, api, testUser, page }) => {
    await pageHelper.loginDirect(testUser.token)
    const project = await api.createProject(testUser.token)
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(5))

    await pageHelper.goToProjectTab(project.id, 'articles')
    await articleCards(page).first().waitFor({ timeout: 10000 })

    // Get initial count
    const initialCount = await articleTitles(page).count()
    expect(initialCount).toBe(5)

    // Apply a filter (filter by "imported" status)
    const statusSelect = page.getByLabel('Status', { exact: true })
    await statusSelect.selectOption('screening')
    // Nothing has started screening, so the filter empties the list
    await expect(articleTitles(page)).toHaveCount(0)

    // Click "Clear Filters" button
    await page.getByRole('button', { name: /clear filters/i }).click()

    // Assert all articles shown again and the filter reset
    await expect(articleTitles(page)).toHaveCount(initialCount)
    await expect(statusSelect).toHaveValue('')
  })

  test('should display article metadata', async ({ pageHelper, api, testUser, page }) => {
    await pageHelper.loginDirect(testUser.token)
    const project = await api.createProject(testUser.token)
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(3))

    await pageHelper.goToProjectTab(project.id, 'articles')
    await articleCards(page).first().waitFor({ timeout: 10000 })

    // Get the first article card
    const firstArticle = articleCards(page).first()

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
