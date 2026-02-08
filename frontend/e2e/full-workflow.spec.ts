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
    await page.getByRole('button', { name: /create project/i }).click()
    await page.waitForSelector('#project-name', { timeout: 5_000 })

    await page.locator('#project-name').fill('Effects of Exercise on Depression')
    await page.locator('#project-description').fill('A systematic review of exercise interventions')
    await page.locator('#review-question').fill('Does exercise reduce depression in adults?')

    // Click the "Create Project" button inside the dialog
    await page.getByRole('button', { name: /^create project$/i }).click()

    // Wait for project card to appear
    await expect(page.getByText('Effects of Exercise on Depression')).toBeVisible({ timeout: 10_000 })

    // ========================================
    // 3. NAVIGATE TO PROJECT
    // ========================================
    await page.getByText('Effects of Exercise on Depression').click()
    await page.waitForLoadState('networkidle')

    // Extract project ID from URL
    const url = page.url()
    const match = url.match(/\/projects\/(\d+)/)
    expect(match).toBeTruthy()
    const projectId = Number(match![1])

    // Verify project overview loaded
    await expect(page.getByText('Overview')).toBeVisible()
    await expect(page.getByText('Criteria')).toBeVisible()
    await expect(page.getByText('Articles')).toBeVisible()
    await expect(page.getByText('Screening')).toBeVisible()

    // ========================================
    // 4. UPLOAD ARTICLES
    // ========================================
    await page.getByRole('button', { name: /upload file/i }).click()
    await page.waitForSelector('#article-file, input[type="file"]', { timeout: 5_000 })

    const risContent = generateRisContent(3)
    const fileInput = page.locator('#article-file, input[type="file"]').first()
    await fileInput.setInputFiles({
      name: 'test_articles.ris',
      mimeType: 'application/x-research-info-systems',
      buffer: Buffer.from(risContent),
    })

    await page.getByRole('button', { name: /^upload$/i }).click()

    // Wait for upload to complete
    await expect(
      page.getByText(/upload.*success|processing|imported|complete/i)
    ).toBeVisible({ timeout: 15_000 })

    // ========================================
    // 5. DEFINE CRITERIA
    // ========================================
    await page.getByRole('link', { name: 'Criteria' }).click()
    await page.waitForLoadState('networkidle')

    // Add inclusion criterion
    const inclusionSection = page.locator('div').filter({ hasText: /^Inclusion Criteria/ }).first()
    await inclusionSection.getByRole('button', { name: /add/i }).click()

    await page.locator('#code').fill('I1')
    await page.locator('#description').fill('RCT study design')
    await page.locator('#rationale').fill('RCTs provide the highest level of evidence')
    await page.getByRole('button', { name: /submit|create|save|add/i }).last().click()

    // Wait for criterion to appear
    await expect(page.getByText('I1')).toBeVisible({ timeout: 5_000 })

    // Add exclusion criterion
    const exclusionSection = page.locator('div').filter({ hasText: /^Exclusion Criteria/ }).first()
    await exclusionSection.getByRole('button', { name: /add/i }).click()

    await page.locator('#code').fill('E1')
    await page.locator('#description').fill('Non-English language')
    await page.locator('#rationale').fill('Translation resources unavailable')
    await page.getByRole('button', { name: /submit|create|save|add/i }).last().click()

    // Both criteria should be visible
    await expect(page.getByText('E1')).toBeVisible({ timeout: 5_000 })

    // ========================================
    // 6. VIEW ARTICLES
    // ========================================
    await page.getByRole('link', { name: 'Articles' }).click()
    await page.waitForLoadState('networkidle')

    // Wait for articles to appear
    await page.waitForSelector('h3', { timeout: 10_000 })
    const articleCount = await page.locator('h3').count()
    expect(articleCount).toBe(3)

    // ========================================
    // 7. START SCREENING (via API — no UI button for this)
    // ========================================
    const token = await api.login(userEmail, userPassword)
    await api.startScreening(token, projectId)

    // ========================================
    // 8. SCREEN ARTICLES
    // ========================================
    await page.getByRole('link', { name: 'Screening' }).click()
    await page.waitForLoadState('networkidle')

    // Wait for first article to load
    await page.waitForSelector('h1', { timeout: 10_000 })
    const firstTitle = await page.locator('h1').first().textContent()
    expect(firstTitle).toContain('E2E Test Article')

    // Article 1: Include with reasoning
    await page.locator('#reasoning').fill('Meets inclusion criteria — RCT design confirmed')
    await page.getByRole('button', { name: /include/i }).first().click()
    await page.waitForTimeout(1_500)

    // Article 2: Exclude with reasoning
    const secondTitle = await page.locator('h1').first().textContent()
    expect(secondTitle).not.toBe(firstTitle)
    await page.locator('#reasoning').fill('Non-English publication — excluded per E1')
    await page.getByRole('button', { name: /exclude/i }).first().click()
    await page.waitForTimeout(1_500)

    // Article 3: Include
    await page.locator('#reasoning').fill('Strong methodology, meets all criteria')
    await page.getByRole('button', { name: /include/i }).first().click()
    await page.waitForTimeout(1_500)

    // ========================================
    // 9. VERIFY STATS
    // ========================================
    // After screening all articles, stats should show counts
    const pageContent = await page.content()
    const hasIncluded = pageContent.toLowerCase().includes('included')
    const hasExcluded = pageContent.toLowerCase().includes('excluded')
    expect(hasIncluded || hasExcluded).toBeTruthy()

    // ========================================
    // 10. VIEW ARTICLE DETAIL
    // ========================================
    await page.getByRole('link', { name: 'Articles' }).click()
    await page.waitForLoadState('networkidle')
    await page.waitForSelector('h3', { timeout: 10_000 })

    // Click on first article to view detail
    await page.locator('h3').first().click()
    await page.waitForLoadState('networkidle')

    // Assert detail page shows article info
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 5_000 })

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
