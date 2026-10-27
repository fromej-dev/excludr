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

  test.describe('table, search, sort and URL state', () => {
    const entries = [
      { title: 'Zebra crossing safety', year: 2015, author: 'Alpha, Ann', journal: 'Road Journal' },
      { title: 'Mango yield under drought', year: 2022, author: 'Beta, Bob', journal: 'Fruit Letters' },
      { title: 'Aspirin and stroke outcomes', year: 2019, author: 'Gamma, Gus', journal: 'Heart Review' },
    ]
    const risFor = (items: typeof entries) =>
      items
        .map((e, i) =>
          [
            'TY  - JOUR',
            `TI  - ${e.title}`,
            `AU  - ${e.author}`,
            `AB  - Abstract ${i}.`,
            `PY  - ${e.year}`,
            `JO  - ${e.journal}`,
            `DO  - 10.5555/table-${Math.random().toString(36).slice(2, 10)}`,
            'ER  - ',
            '',
          ].join('\n'),
        )
        .join('\n')

    test('search narrows the results', async ({ pageHelper, api, testUser, page }) => {
      await pageHelper.loginDirect(testUser.token)
      const project = await api.createProject(testUser.token)
      await api.uploadRisFile(testUser.token, project.id, risFor(entries))
      await pageHelper.goToProjectTab(project.id, 'articles')
      await expect(articleTitles(page)).toHaveCount(3)
      await expect(page.getByTestId('articles-count')).toHaveText('3 articles')

      // Title match
      await page.getByLabel('Search').fill('mango')
      await expect(articleTitles(page)).toHaveCount(1)
      await expect(articleTitles(page).first()).toContainText('Mango')
      await expect(page).toHaveURL(/[?&]q=mango/)
      await expect(page.getByTestId('articles-count')).toHaveText('1 article')

      // Author match
      await page.getByLabel('Search').fill('gamma')
      await expect(articleTitles(page)).toHaveCount(1)
      await expect(articleTitles(page).first()).toContainText('Aspirin')

      // Journal match
      await page.getByLabel('Search').fill('road journal')
      await expect(articleTitles(page)).toHaveCount(1)
      await expect(articleTitles(page).first()).toContainText('Zebra')

      // No match shows the filtered empty state; its button clears the search
      await page.getByLabel('Search').fill('nothing-like-this')
      await expect(page.getByTestId('articles-no-matches')).toBeVisible()
      await page.getByRole('button', { name: 'Clear all filters' }).click()
      await expect(articleTitles(page)).toHaveCount(3)
      await expect(page.getByLabel('Search')).toHaveValue('')
    })

    test('sorting by year changes the order', async ({ pageHelper, api, testUser, page }) => {
      await pageHelper.loginDirect(testUser.token)
      const project = await api.createProject(testUser.token)
      await api.uploadRisFile(testUser.token, project.id, risFor(entries))
      await pageHelper.goToProjectTab(project.id, 'articles')
      await expect(articleTitles(page)).toHaveCount(3)

      const yearHeader = page.getByRole('columnheader', { name: /year/i })
      await expect(yearHeader).toHaveAttribute('aria-sort', 'none')

      await page.getByTestId('sort-year').click()
      await expect(yearHeader).toHaveAttribute('aria-sort', 'ascending')
      await expect(articleTitles(page).first()).toContainText('Zebra') // 2015
      await expect(articleTitles(page).last()).toContainText('Mango') // 2022

      await page.getByTestId('sort-year').click()
      await expect(yearHeader).toHaveAttribute('aria-sort', 'descending')
      await expect(articleTitles(page).first()).toContainText('Mango')
      await expect(articleTitles(page).last()).toContainText('Zebra')
      await expect(page).toHaveURL(/sort=year/)
      await expect(page).toHaveURL(/order=desc/)

      await page.getByTestId('sort-title').click()
      await expect(articleTitles(page).first()).toContainText('Aspirin')
    })

    test('rows are keyboard accessible', async ({ pageHelper, api, testUser, page }) => {
      await pageHelper.loginDirect(testUser.token)
      const project = await api.createProject(testUser.token)
      await api.uploadRisFile(testUser.token, project.id, risFor(entries))
      await pageHelper.goToProjectTab(project.id, 'articles')
      await expect(articleCards(page)).toHaveCount(3)

      await articleCards(page).first().focus()
      await page.keyboard.press('Enter')
      await expect(page.getByTestId('article-detail-title')).toBeVisible()
    })

    test('filters persist in the URL after visiting an article and going back', async ({
      pageHelper,
      api,
      testUser,
      page,
    }) => {
      await pageHelper.loginDirect(testUser.token)
      const project = await api.createProject(testUser.token)
      await api.uploadRisFile(testUser.token, project.id, risFor(entries))
      await pageHelper.goToProjectTab(project.id, 'articles')
      await expect(articleTitles(page)).toHaveCount(3)

      await page.getByLabel('Status', { exact: true }).selectOption('imported')
      await page.getByLabel('Search').fill('a')
      await page.getByTestId('sort-year').click()
      await expect(page).toHaveURL(/status=imported/)
      await expect(page).toHaveURL(/q=a/)
      await expect(page).toHaveURL(/sort=year/)

      // Reload keeps the state
      await page.reload()
      await expect(page.getByLabel('Status', { exact: true })).toHaveValue('imported')
      await expect(page.getByLabel('Search')).toHaveValue('a')
      await expect(articleTitles(page).first()).toBeVisible()

      // Open an article, then use the in-app Back button
      await articleCards(page).first().click()
      await expect(page.getByTestId('article-detail-title')).toBeVisible()
      await page.getByRole('button', { name: /back/i }).click()

      await expect(page).toHaveURL(/status=imported/)
      await expect(page).toHaveURL(/q=a/)
      await expect(page).toHaveURL(/sort=year/)
      await expect(page.getByLabel('Status', { exact: true })).toHaveValue('imported')
      await expect(page.getByLabel('Search')).toHaveValue('a')
      await expect(articleTitles(page).first()).toBeVisible()

      // Browser back also returns to the filtered list
      await articleCards(page).first().click()
      await expect(page.getByTestId('article-detail-title')).toBeVisible()
      await page.goBack()
      await expect(page).toHaveURL(/status=imported/)
      await expect(page.getByLabel('Search')).toHaveValue('a')
    })

    test('page size and range text reflect pagination', async ({ pageHelper, api, testUser, page }) => {
      await pageHelper.loginDirect(testUser.token)
      const project = await api.createProject(testUser.token)
      await api.uploadRisFile(testUser.token, project.id, generateRisContent(3))
      await pageHelper.goToProjectTab(project.id, 'articles')
      await expect(page.getByTestId('articles-range')).toHaveText('Showing 1–3 of 3')
      await expect(page.getByRole('button', { name: 'Next' })).toBeDisabled()
      await page.getByLabel('Per page').selectOption('50')
      await expect(page).toHaveURL(/per_page=50/)
    })
  })
})
