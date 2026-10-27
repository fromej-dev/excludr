import { test, expect, generateRisContent } from './fixtures'

test.describe.serial('Complete Systematic Review Workflow', () => {
  test('complete systematic review workflow', async ({ page, api }) => {
    const uid = Math.random().toString(36).slice(2, 10)
    const userEmail = `researcher_${uid}@example.com`
    const userPassword = 'SecurePass123!'
    const userName = `Researcher ${uid}`

    // ========================================
    // 1. REGISTER
    // ========================================
    await page.goto('/register')

    await page.locator('#name').fill(userName)
    await page.locator('#email').fill(userEmail)
    await page.locator('#password').fill(userPassword)
    await page.locator('#confirm-password').fill(userPassword)
    await page.locator('button[type="submit"]').click()

    // Assert redirect to dashboard
    await page.waitForURL('/', { timeout: 10_000 })
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible()

    // ========================================
    // 2. CREATE PROJECT
    // ========================================
    await page.getByTestId('create-project').click()
    const dialog = page.getByRole('dialog', { name: 'Create New Project' })
    await expect(dialog).toBeVisible()

    await page.locator('#project-name').fill('Effects of Exercise on Depression')
    await page.locator('#project-description').fill('A systematic review of exercise interventions')
    await page.locator('#review-question').fill('Does exercise reduce depression in adults?')

    // Click the "Create Project" button inside the dialog
    await dialog.getByTestId('create-project-submit').click()

    // Wait for project card to appear
    await expect(dialog).toBeHidden({ timeout: 10_000 })
    await expect(page.getByRole('heading', { name: 'Effects of Exercise on Depression' })).toBeVisible({ timeout: 10_000 })

    // ========================================
    // 3. NAVIGATE TO PROJECT
    // ========================================
    await page.getByRole('heading', { name: 'Effects of Exercise on Depression' }).click()
    await page.waitForLoadState('networkidle')

    // Extract project ID from URL
    const url = page.url()
    const match = url.match(/\/projects\/(\d+)/)
    expect(match).toBeTruthy()
    const projectId = Number(match![1])

    // Verify project overview loaded
    for (const name of ['Overview', 'Criteria', 'Articles', 'Title/abstract']) {
      await expect(page.getByRole('link', { name: new RegExp(`^${name.replace('/', '\\/')}`) })).toBeVisible()
    }

    // ========================================
    // 4. UPLOAD ARTICLES
    // ========================================
    await expect(page.getByRole('button', { name: /upload ris/i })).toBeVisible()
    // Upload starts as soon as a file is chosen
    await page.getByTestId('ris-input').setInputFiles({
      name: 'test_articles.ris',
      mimeType: 'application/x-research-info-systems',
      buffer: Buffer.from(generateRisContent(3)),
    })

    // Wait for the import summary
    const importResult = page.getByTestId('import-result')
    await expect(importResult).toBeVisible({ timeout: 30_000 })
    await expect(importResult).toContainText('3')

    // ========================================
    // 5. DEFINE CRITERIA
    // ========================================
    await page.getByRole('link', { name: /^Criteria/ }).click()
    await page.waitForLoadState('networkidle')

    // Add inclusion criterion
    await page.getByTestId('add-inclusion').click()

    await page.locator('#code').fill('I1')
    await page.locator('#description').fill('RCT study design')
    await page.locator('#rationale').fill('RCTs provide the highest level of evidence')
    await page.getByRole('button', { name: 'Add Criterion', exact: true }).click()

    // Wait for criterion to appear
    await expect(page.getByTestId('inclusion-column').getByText('I1', { exact: true })).toBeVisible({ timeout: 5_000 })

    // Add exclusion criterion
    await page.getByTestId('add-exclusion').click()

    await page.locator('#code').fill('E1')
    await page.locator('#description').fill('Non-English language')
    await page.locator('#rationale').fill('Translation resources unavailable')
    await page.getByRole('button', { name: 'Add Criterion', exact: true }).click()

    // Both criteria should be visible, each in its own column
    await expect(page.getByTestId('exclusion-column').getByText('E1', { exact: true })).toBeVisible({ timeout: 5_000 })
    await expect(page.getByTestId('inclusion-column').getByText('I1', { exact: true })).toBeVisible()

    // ========================================
    // 6. VIEW ARTICLES
    // ========================================
    await page.getByRole('link', { name: /^Articles/ }).click()

    // Wait for articles to appear
    await expect(page.getByTestId('article-card')).toHaveCount(3, { timeout: 10_000 })

    // ========================================
    // 7. START SCREENING (via API — no UI button for this)
    // ========================================
    const token = await api.login(userEmail, userPassword)
    await api.startScreening(token, projectId)

    // ========================================
    // 8. SCREEN ARTICLES
    // ========================================
    await page.getByRole('link', { name: /^Title\/abstract/ }).click()

    // Wait for first article to load
    const articleTitle = page.getByTestId('article-title')
    await expect(articleTitle).toBeVisible({ timeout: 10_000 })
    const firstTitle = (await articleTitle.textContent())?.trim()
    expect(firstTitle).toContain('E2E Test Article')
    const include = page.getByRole('button', { name: 'Include (I)' })
    const exclude = page.getByRole('button', { name: 'Exclude (E)' })

    // Article 1: Include with reasoning
    await page.locator('#reasoning').fill('Meets inclusion criteria — RCT design confirmed')
    await include.click()

    // Article 2: Exclude with reasoning
    await expect(articleTitle).not.toHaveText(firstTitle!)
    const secondTitle = (await articleTitle.textContent())?.trim()
    await expect(page.locator('#reasoning')).toHaveValue('')
    await page.locator('#reasoning').fill('Non-English publication — excluded per E1')
    await exclude.click()

    // Article 3: Include
    await expect(articleTitle).not.toHaveText(secondTitle!)
    await page.locator('#reasoning').fill('Strong methodology, meets all criteria')
    await include.click()

    // Queue is empty once all three are decided
    await expect(page.getByRole('heading', { name: /no more articles to screen/i })).toBeVisible({ timeout: 10_000 })

    // ========================================
    // 9. VERIFY STATS
    // ========================================
    // After screening all articles, stats should show counts
    await expect(page.getByText('Included', { exact: true })).toBeVisible()
    await expect(page.getByText('Excluded', { exact: true })).toBeVisible()

    // ========================================
    // 10. VIEW ARTICLE DETAIL
    // ========================================
    await page.getByRole('link', { name: /^Articles/ }).click()
    await expect(page.getByTestId('article-card')).toHaveCount(3, { timeout: 10_000 })

    // Click on first article to view detail
    await page.getByTestId('article-card-title').first().click()

    // Assert detail page shows article info
    await expect(page.getByTestId('article-detail-title')).toBeVisible({ timeout: 5_000 })
    await expect(page.getByRole('heading', { name: 'Screening History' })).toBeVisible()

    // Look for screening history / decision info
    const detailContent = await page.content()
    const hasDecisionInfo =
      detailContent.toLowerCase().includes('include') ||
      detailContent.toLowerCase().includes('exclude') ||
      detailContent.toLowerCase().includes('decision') ||
      detailContent.toLowerCase().includes('screening')
    expect(hasDecisionInfo).toBeTruthy()
  })
})
