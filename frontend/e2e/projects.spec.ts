import { test, expect, generateRisContent } from './fixtures'

test.describe('Project Management Flow', () => {
  test('should show empty state when no projects', async ({ page, pageHelper, testUser }) => {
    // Login and navigate to dashboard
    await pageHelper.loginDirect(testUser.token)

    // Assert empty state is visible
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible()
    await expect(page.getByText(/no projects/i)).toBeVisible()
    await expect(page.getByTestId('create-project')).toBeVisible()
    await expect(page.getByTestId('create-first-project')).toBeVisible()
  })

  test('should create a project via dialog', async ({ page, pageHelper, testUser }) => {
    await pageHelper.loginDirect(testUser.token)

    // Open create dialog
    await page.getByTestId('create-project').click()
    const dialog = page.getByRole('dialog', { name: 'Create New Project' })
    await expect(dialog).toBeVisible()

    // Fill all fields
    await page.locator('#project-name').fill('My Systematic Review')
    await page.locator('#project-description').fill('Testing the effectiveness of intervention X on outcome Y')
    await page.locator('#review-question').fill('What is the effect of intervention X on outcome Y in adults?')

    // Submit form
    await dialog.getByTestId('create-project-submit').click()

    // Dialog closes once the project has been created
    await expect(dialog).toBeHidden({ timeout: 10000 })

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
    await expect(page.getByRole('heading', { name: 'Navigate Test Project', level: 1 })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Navigate Test Project', level: 2 })).toBeVisible()

    // Verify tab navigation is visible
    for (const name of ['Overview', 'Criteria', 'Articles', 'Screening']) {
      await expect(page.getByRole('tab', { name, exact: true })).toBeVisible()
    }
    await expect(page.getByRole('tab', { name: 'Overview', exact: true })).toHaveAttribute('aria-selected', 'true')
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
    await page.getByRole('button', { name: 'Edit', exact: true }).click()

    // Modify fields
    await page.getByLabel('Project Name').fill('Updated Project Name')
    await page.getByLabel('Description', { exact: true }).fill('Updated description text')
    await page.getByLabel('Review Question').fill('Updated review question')

    // Save changes
    await page.getByRole('button', { name: 'Save Changes' }).click()

    // Wait for save to complete
    await expect(page.getByRole('button', { name: 'Edit', exact: true })).toBeVisible({ timeout: 10000 })

    // Assert changes are reflected (page title and overview card)
    await expect(page.getByRole('heading', { name: 'Updated Project Name', level: 1 })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Updated Project Name', level: 2 })).toBeVisible()
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
    await page.getByRole('button', { name: 'Delete', exact: true }).click()

    // Confirm deletion in dialog
    await page.getByRole('dialog', { name: 'Delete Project' }).getByRole('button', { name: 'Delete Project' }).click()

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

    // The import card is always visible for the owner
    await expect(page.getByRole('button', { name: /upload ris/i })).toBeVisible()

    // Generate RIS content and create a file
    const risContent = generateRisContent(3)
    const tmpPath = `/tmp/test-upload-${Date.now()}.ris`

    // Create temporary file using Bash
    await page.context().addInitScript(`
      window.testRisContent = ${JSON.stringify(risContent)}
    `)

    // Set file input
    const fileInput = page.getByTestId('ris-input')

    // Create a DataTransfer with the file
    await fileInput.setInputFiles({
      name: 'test_articles.ris',
      mimeType: 'application/x-research-info-systems',
      buffer: Buffer.from(risContent),
    })

    // Upload starts as soon as a file is chosen
    // Wait for success message or processing indicator
    await expect(
      page.getByTestId('import-result')
    ).toBeVisible({ timeout: 15000 })
  })

  test('should navigate between project tabs', async ({ page, pageHelper, testUser, api }) => {
    // Create project
    const project = await api.createProject(testUser.token, {
      name: 'Tab Navigation Test',
    })

    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'overview')

    const tab = (name: string) => page.getByRole('tab', { name, exact: true })

    // Navigate to Criteria tab
    await tab('Criteria').click()
    await expect(page).toHaveURL(`/projects/${project.id}/criteria`)
    await expect(tab('Criteria')).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByRole('heading', { name: 'Inclusion Criteria' })).toBeVisible()

    // Navigate to Articles tab
    await tab('Articles').click()
    await expect(page).toHaveURL(`/projects/${project.id}/articles`)
    await expect(tab('Articles')).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByRole('button', { name: 'Clear Filters' })).toBeVisible()

    // Navigate to Screening tab
    await tab('Screening').click()
    await expect(page).toHaveURL(`/projects/${project.id}/screening`)
    await expect(tab('Screening')).toHaveAttribute('aria-selected', 'true')
    // The AI batch card now lives in a dialog opened from the screening toolbar
    await page.getByTestId('ai-batch-open').click()
    await expect(page.getByTestId('ai-batch-card')).toBeVisible()
    await page.getByRole('button', { name: 'Close' }).click()
    await expect(page.getByTestId('ai-batch-card')).toBeHidden()

    // Navigate back to Overview
    await tab('Overview').click()
    await expect(page).toHaveURL(`/projects/${project.id}`)
    await expect(tab('Overview')).toHaveAttribute('aria-selected', 'true')
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
