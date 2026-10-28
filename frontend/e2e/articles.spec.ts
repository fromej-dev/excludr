import type { APIRequestContext, Page } from '@playwright/test'
import { test, expect, generateRisContent, type ApiHelper } from './fixtures'

const articleCards = (page: Page) => page.getByTestId('article-card')
const articleTitles = (page: Page) => page.getByTestId('article-card-title')

const auth = (token: string) => ({ Authorization: `Bearer ${token}` })

/** Record a human title/abstract decision (include -> awaiting full text, exclude -> excluded). */
async function decide(
  request: APIRequestContext,
  token: string,
  projectId: number,
  articleId: number,
  decision: 'include' | 'exclude',
) {
  const res = await request.post(`/api/v1/projects/${projectId}/screening/articles/${articleId}/decisions`, {
    headers: auth(token),
    data: { stage: 'title_abstract', decision, source: 'human', reasoning: 'e2e' },
  })
  expect(res.status()).toBe(201)
}

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

    // Upload articles (they go straight to status "screening")
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(5))

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

    // Apply a filter that matches nothing: imports go straight to "screening"
    const statusSelect = page.getByLabel('Status', { exact: true })
    await statusSelect.selectOption('imported')
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
    await expect(firstArticle.getByTestId('article-status').first()).toBeVisible()
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

      await page.getByLabel('Status', { exact: true }).selectOption('screening')
      await page.getByLabel('Search').fill('a')
      await page.getByTestId('sort-year').click()
      await expect(page).toHaveURL(/status=screening/)
      await expect(page).toHaveURL(/q=a/)
      await expect(page).toHaveURL(/sort=year/)

      // Reload keeps the state
      await page.reload()
      await expect(page.getByLabel('Status', { exact: true })).toHaveValue('screening')
      await expect(page.getByLabel('Search')).toHaveValue('a')
      await expect(articleTitles(page).first()).toBeVisible()

      // Open an article, then use the in-app Back button
      await articleCards(page).first().click()
      await expect(page.getByTestId('article-detail-title')).toBeVisible()
      await page.getByRole('button', { name: /back/i }).click()

      await expect(page).toHaveURL(/status=screening/)
      await expect(page).toHaveURL(/q=a/)
      await expect(page).toHaveURL(/sort=year/)
      await expect(page.getByLabel('Status', { exact: true })).toHaveValue('screening')
      await expect(page.getByLabel('Search')).toHaveValue('a')
      await expect(articleTitles(page).first()).toBeVisible()

      // Browser back also returns to the filtered list
      await articleCards(page).first().click()
      await expect(page.getByTestId('article-detail-title')).toBeVisible()
      await page.goBack()
      await expect(page).toHaveURL(/status=screening/)
      await expect(page.getByLabel('Search')).toHaveValue('a')
    })

    test('opening an article URL directly and clicking Back goes to the plain list', async ({
      pageHelper,
      api,
      testUser,
      page,
    }) => {
      await pageHelper.loginDirect(testUser.token)
      const project = await api.createProject(testUser.token)
      await api.uploadRisFile(testUser.token, project.id, risFor(entries))
      const { data } = await api.getArticles(testUser.token, project.id)

      await page.goto(`/projects/${project.id}/articles/${data[0].id}`)
      await expect(page.getByTestId('article-detail-title')).toBeVisible()
      await page.getByRole('button', { name: /back/i }).click()

      await expect(page).toHaveURL(new RegExp(`/projects/${project.id}/articles$`))
      await expect(articleTitles(page)).toHaveCount(3)
      await expect(page.getByLabel('Status', { exact: true })).toHaveValue('')
    })

    test('Back keeps the sort query across several detail visits', async ({ pageHelper, api, testUser, page }) => {
      await pageHelper.loginDirect(testUser.token)
      const project = await api.createProject(testUser.token)
      await api.uploadRisFile(testUser.token, project.id, risFor(entries))
      await pageHelper.goToProjectTab(project.id, 'articles')
      await expect(articleTitles(page)).toHaveCount(3)
      await page.getByTestId('sort-year').click()
      await expect(page).toHaveURL(/sort=year/)

      for (let i = 0; i < 2; i++) {
        await articleCards(page).nth(i).click()
        await expect(page.getByTestId('article-detail-title')).toBeVisible()
        await page.getByRole('button', { name: /back/i }).click()
        await expect(page).toHaveURL(/sort=year/)
        await expect(articleTitles(page).first()).toContainText('Zebra')
      }
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

  test.describe('status column', () => {
    test('shows one merged Status column with pipeline states and no Decision column', async ({
      pageHelper,
      api,
      testUser,
      page,
      request,
    }) => {
      const token = testUser.token
      await pageHelper.loginDirect(token)
      const project = await api.createProject(token)
      await api.uploadRisFile(token, project.id, generateRisContent(4))
      const { data } = await api.getArticles(token, project.id)
      await decide(request, token, project.id, data[0].id, 'include') // awaiting full text
      await decide(request, token, project.id, data[1].id, 'exclude') // excluded

      await pageHelper.goToProjectTab(project.id, 'articles')
      await expect(articleCards(page)).toHaveCount(4)

      await expect(page.getByRole('columnheader', { name: 'Decision' })).toHaveCount(0)
      await expect(page.getByRole('columnheader', { name: /status/i })).toHaveCount(1)

      const statuses = page.getByTestId('article-status')
      await expect(statuses.filter({ hasText: 'Title/abstract' })).toHaveCount(2)
      await expect(statuses.filter({ hasText: 'Awaiting full text' })).toHaveCount(1)
      await expect(statuses.filter({ hasText: 'Excluded' })).toHaveCount(1)
      await expect(statuses.filter({ hasText: '✕' })).toHaveCount(1)
      // The outcome is shown once per row, not repeated in a second column
      await expect(articleCards(page).filter({ hasText: 'Excluded' })).toHaveCount(1)
      await expect(articleCards(page).first().getByText('Excluded')).toHaveCount(0)

      // Both filters remain and filter different fields
      await expect(page.getByLabel('Status', { exact: true })).toBeVisible()
      await page.getByLabel('Decision', { exact: true }).selectOption('excluded')
      await expect(articleCards(page)).toHaveCount(1)
    })
  })

  test.describe('bulk full-text retrieval', () => {
    async function seedAwaiting(api: ApiHelper, request: APIRequestContext, token: string) {
      const project = await api.createProject(token)
      await api.uploadRisFile(token, project.id, generateRisContent(3))
      const { data } = await api.getArticles(token, project.id)
      for (const a of data.slice(0, 2)) await decide(request, token, project.id, a.id, 'include')
      return { project, ids: data.slice(0, 2).map((a) => a.id) }
    }

    test('owner selects two rows and starts retrieval', async ({ pageHelper, api, testUser, page, request }) => {
      const { project, ids } = await seedAwaiting(api, request, testUser.token)
      await pageHelper.loginDirect(testUser.token)

      let seen: { method: string; url: string; body: unknown } | null = null
      await page.route(/\/articles\/retrieve-fulltext$/, async (route) => {
        const req = route.request()
        seen = { method: req.method(), url: new URL(req.url()).pathname, body: req.postDataJSON() }
        await route.fulfill({ status: 200, json: { message: 'Full-text retrieval started', count: 2 } })
      })

      await pageHelper.goToProjectTab(project.id, 'articles')
      await expect(articleCards(page)).toHaveCount(3)
      await expect(page.getByTestId('bulk-bar')).toHaveCount(0)

      await page.getByTestId('row-select').nth(0).check()
      await page.getByTestId('row-select').nth(1).check()
      await expect(page.getByTestId('bulk-bar')).toContainText('2 selected')

      await page.getByTestId('bulk-retrieve').click()

      await expect.poll(() => seen).not.toBeNull()
      expect(seen!.method).toBe('POST')
      expect(seen!.url).toBe(`/api/v1/projects/${project.id}/articles/retrieve-fulltext`)
      const sent = (seen!.body as { article_ids: number[] }).article_ids
      expect([...sent].sort((a, b) => a - b)).toEqual([...ids].sort((a, b) => a - b))

      await expect(page.getByText('Full-text retrieval started for 2 of 2 selected articles')).toBeVisible()
      await expect(page.getByTestId('bulk-bar')).toHaveCount(0)
      await expect(page.getByTestId('row-select').nth(0)).not.toBeChecked()
    })

    test('nothing eligible shows an info toast and keeps the selection', async ({
      pageHelper,
      api,
      testUser,
      page,
    }) => {
      const project = await api.createProject(testUser.token)
      await api.uploadRisFile(testUser.token, project.id, generateRisContent(2))
      await pageHelper.loginDirect(testUser.token)
      await pageHelper.goToProjectTab(project.id, 'articles')
      await expect(articleCards(page)).toHaveCount(2)

      await page.getByTestId('select-all').check()
      await page.getByTestId('bulk-retrieve').click() // real endpoint: imported articles are not eligible
      await expect(page.getByText('None of the selected articles are awaiting a full text')).toBeVisible()
      await expect(page.getByTestId('bulk-bar')).toContainText('2 selected')
    })

    test('reviewers and viewers see no checkboxes or bulk bar', async ({
      pageHelper,
      api,
      testUser,
      page,
      request,
    }) => {
      const project = await api.createProject(testUser.token)
      await api.uploadRisFile(testUser.token, project.id, generateRisContent(2))

      for (const role of ['reviewer', 'viewer'] as const) {
        const member = await api.register()
        const res = await request.post(`/api/v1/projects/${project.id}/members`, {
          headers: auth(testUser.token),
          data: { email: member.email, role },
        })
        expect(res.status()).toBe(201)

        await pageHelper.loginDirect(member.token)
        await pageHelper.goToProjectTab(project.id, 'articles')
        await expect(articleCards(page)).toHaveCount(2)
        await expect(page.getByTestId('row-select')).toHaveCount(0)
        await expect(page.getByTestId('select-all')).toHaveCount(0)
        await expect(page.getByTestId('bulk-bar')).toHaveCount(0)
      }

      // The owner does see them
      await pageHelper.loginDirect(testUser.token)
      await pageHelper.goToProjectTab(project.id, 'articles')
      await expect(page.getByTestId('row-select')).toHaveCount(2)
    })
  })
})
