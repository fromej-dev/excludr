import { test, expect, generateRisContent } from './fixtures'

test.describe('Project Management Flow', () => {
  test('should show empty state when no projects', async ({ page, pageHelper, testUser }) => {
    // Login and navigate to dashboard
    await pageHelper.loginDirect(testUser.token)

    // Assert empty state is visible
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible()
    await expect(page.getByText(/no projects/i)).toBeVisible()
    await expect(page.getByRole('button', { name: /create project/i })).toBeVisible()
  })

  test('should create a project via dialog', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)

    // Open create dialog
    await page.getByRole('button', { name: /create project/i }).click()

    // Fill all fields
    await page.locator('#project-name').fill('My Systematic Review')
    await page.locator('#project-description').fill('Testing the effectiveness of intervention X on outcome Y')
    await page.locator('#review-question').fill('What is the effect of intervention X on outcome Y in adults?')

    // Submit form
    await page.getByRole('button', { name: /^create project$/i }).click()

    // Wait for loading state to disappear
    await expect(page.getByRole('button', { name: /creating/i })).toBeVisible({ timeout: 2000 })
    await expect(page.getByRole('button', { name: /creating/i })).toBeHidden({ timeout: 10000 })

    // Assert project card appears in the list
    await expect(page.getByText('My Systematic Review')).toBeVisible()
    await expect(page.getByText('Testing the effectiveness of intervention X on outcome Y')).toBeVisible()
  })

  test('should navigate to project overview', async ({ page, pageHelper, testUser, api }) => {
    // Create project via API
    const project = await api.createProject(testUser.token, {
      name: 'Navigate Test Project',
      description: 'Testing navigation',
      review_question: 'What is the question?',
    })

    await pageHelper.loginDirect(testUser.token)

    // Click on project card
    await page.getByText('Navigate Test Project').click()

    // Assert we're on the project overview page
    await expect(page).toHaveURL(`/projects/${project.id}`)
    await expect(page.getByRole('heading', { name: 'Navigate Test Project' })).toBeVisible()

    // Verify tab navigation is visible
    await expect(page.getByRole('link', { name: 'Overview' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Criteria' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Articles' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Screening' })).toBeVisible()
  })

  test('should edit project details', async ({ page, pageHelper, testUser, api }) => {
    // Create project
    const project = await api.createProject(testUser.token, {
      name: 'Original Project Name',
      description: 'Original description',
      review_question: 'Original question',
    })

    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'overview')

    // Click edit button
    await page.getByRole('button', { name: /edit/i }).click()

    // Modify fields
    const nameInput = page.locator('input[name="name"], input#name, input').filter({ hasText: '' }).first()
    await nameInput.clear()
    await nameInput.fill('Updated Project Name')

    const descInput = page.locator('textarea[name="description"], textarea#description, textarea').filter({ hasText: '' }).first()
    await descInput.clear()
    await descInput.fill('Updated description text')

    const questionInput = page.locator('textarea[name="review_question"], textarea#review-question, textarea').filter({ hasText: '' }).nth(1)
    await questionInput.clear()
    await questionInput.fill('Updated review question')

    // Save changes
    await page.getByRole('button', { name: /save changes/i }).click()

    // Wait for save to complete
    await expect(page.getByRole('button', { name: /edit/i })).toBeVisible({ timeout: 10000 })

    // Assert changes are reflected
    await expect(page.getByRole('heading', { name: 'Updated Project Name' })).toBeVisible()
    await expect(page.getByText('Updated description text')).toBeVisible()
    await expect(page.getByText('Updated review question')).toBeVisible()
  })

  test('should delete a project', async ({ page, pageHelper, testUser, api }) => {
    // Create project
    const project = await api.createProject(testUser.token, {
      name: 'Project To Delete',
      description: 'This will be deleted',
      review_question: 'Delete me',
    })

    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'overview')

    // Click delete button
    await page.getByRole('button', { name: /delete/i }).first().click()

    // Confirm deletion in dialog
    await page.getByRole('button', { name: /^delete project$/i }).click()

    // Wait for redirect to dashboard
    await expect(page).toHaveURL('/', { timeout: 10000 })

    // Assert project is gone from the list
    await expect(page.getByText('Project To Delete')).not.toBeVisible()
  })

  test('should upload a RIS file', async ({ page, pageHelper, testUser, api }) => {
    // Create project
    const project = await api.createProject(testUser.token)

    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'overview')

    // Click Upload File button
    await page.getByRole('button', { name: /upload file/i }).click()

    // Generate RIS content and create a file
    const risContent = generateRisContent(3)
    const tmpPath = `/tmp/test-upload-${Date.now()}.ris`

    // Create temporary file using Bash
    await page.context().addInitScript(`
      window.testRisContent = ${JSON.stringify(risContent)}
    `)

    // Set file input
    const fileInput = page.locator('#article-file, input[type="file"]').first()

    // Create a DataTransfer with the file
    await fileInput.setInputFiles({
      name: 'test_articles.ris',
      mimeType: 'application/x-research-info-systems',
      buffer: Buffer.from(risContent),
    })

    // Submit upload
    await page.getByRole('button', { name: /^upload$/i }).click()

    // Wait for success message or processing indicator
    await expect(
      page.getByText(/upload.*success|processing|imported/i)
    ).toBeVisible({ timeout: 15000 })
  })

  test('should navigate between project tabs', async ({ page, pageHelper, testUser, api }) => {
    // Create project
    const project = await api.createProject(testUser.token, {
      name: 'Tab Navigation Test',
    })

    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'overview')

    // Navigate to Criteria tab
    await page.getByRole('link', { name: 'Criteria' }).click()
    await expect(page).toHaveURL(`/projects/${project.id}/criteria`)
    await expect(page.getByRole('heading', { name: /criteria/i })).toBeVisible()

    // Navigate to Articles tab
    await page.getByRole('link', { name: 'Articles' }).click()
    await expect(page).toHaveURL(`/projects/${project.id}/articles`)
    await expect(page.getByRole('heading', { name: /articles/i })).toBeVisible()

    // Navigate to Screening tab
    await page.getByRole('link', { name: 'Screening' }).click()
    await expect(page).toHaveURL(`/projects/${project.id}/screening`)
    await expect(page.getByRole('heading', { name: /screening/i })).toBeVisible()

    // Navigate back to Overview
    await page.getByRole('link', { name: 'Overview' }).click()
    await expect(page).toHaveURL(`/projects/${project.id}`)
  })

  test('should show article count after import', async ({ page, pageHelper, testUser, api }) => {
    // Create project
    const project = await api.createProject(testUser.token, {
      name: 'Article Count Test',
    })

    // Upload articles via API
    const risContent = generateRisContent(5)
    await api.uploadRisFile(testUser.token, project.id, risContent)

    // Wait a moment for processing
    await page.waitForTimeout(2000)

    // Visit overview page
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'overview')

    // Assert article count is shown
    await expect(page.getByText(/5.*article/i)).toBeVisible({ timeout: 10000 })
  })
})
