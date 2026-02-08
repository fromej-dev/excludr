import { test, expect } from './fixtures'

test.describe('Criteria Management', () => {
  test('should show empty state for project with no criteria', async ({ page, pageHelper, testUser, api }) => {
    const project = await api.createProject(testUser.token)
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'criteria')

    // Both columns should show empty state with "Add Criterion" buttons
    const addCriterionButtons = page.getByRole('button', { name: /add criterion/i })
    await expect(addCriterionButtons).toHaveCount(2)

    // Verify column titles are present
    await expect(page.getByText('Inclusion Criteria')).toBeVisible()
    await expect(page.getByText('Exclusion Criteria')).toBeVisible()
  })

  test('should create an inclusion criterion', async ({ page, pageHelper, testUser, api }) => {
    const project = await api.createProject(testUser.token)
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'criteria')

    // Click "Add" button in inclusion criteria section
    // Find the section containing "Inclusion Criteria" heading
    const inclusionSection = page.locator('div').filter({ hasText: /^Inclusion Criteria/ }).first()
    await inclusionSection.getByRole('button', { name: /add/i }).click()

    // Fill the criterion form
    await page.locator('#code').fill('I1')
    await page.locator('#description').fill('Studies must include quantitative data')
    await page.locator('#rationale').fill('We need measurable outcomes for meta-analysis')

    // Submit the form
    await page.getByRole('button', { name: /submit|create|save/i }).click()

    // Assert the criterion card appears with correct data
    await expect(page.getByText('I1')).toBeVisible()
    await expect(page.getByText('Studies must include quantitative data')).toBeVisible()
    await expect(page.getByText('We need measurable outcomes for meta-analysis')).toBeVisible()
  })

  test('should create an exclusion criterion', async ({ page, pageHelper, testUser, api }) => {
    const project = await api.createProject(testUser.token)
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'criteria')

    // Click "Add" button in exclusion criteria section
    const exclusionSection = page.locator('div').filter({ hasText: /^Exclusion Criteria/ }).first()
    await exclusionSection.getByRole('button', { name: /add/i }).click()

    // Fill the criterion form (no rationale this time)
    await page.locator('#code').fill('E1')
    await page.locator('#description').fill('Animal studies must be excluded')

    // Submit the form
    await page.getByRole('button', { name: /submit|create|save/i }).click()

    // Assert the criterion card appears in the exclusion column
    await expect(page.getByText('E1')).toBeVisible()
    await expect(page.getByText('Animal studies must be excluded')).toBeVisible()
  })

  test('should edit a criterion', async ({ page, pageHelper, testUser, api }) => {
    const project = await api.createProject(testUser.token)
    const criterion = await api.createCriterion(testUser.token, project.id, {
      type: 'inclusion',
      code: 'I1',
      description: 'Original description text',
      rationale: 'Original rationale text',
    })

    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'criteria')

    // Verify original content is visible
    await expect(page.getByText('Original description text')).toBeVisible()

    // Click edit button on the criterion card
    await page.getByRole('button', { name: /edit/i }).first().click()

    // Change the description
    await page.locator('#description').clear()
    await page.locator('#description').fill('Updated description text')

    // Save the changes
    await page.getByRole('button', { name: /submit|save|update/i }).click()

    // Assert updated description is shown and original is gone
    await expect(page.getByText('Updated description text')).toBeVisible()
    await expect(page.getByText('Original description text')).not.toBeVisible()
  })

  test('should delete a criterion', async ({ page, pageHelper, testUser, api }) => {
    const project = await api.createProject(testUser.token)
    const criterion = await api.createCriterion(testUser.token, project.id, {
      type: 'inclusion',
      code: 'I1',
      description: 'This criterion will be deleted',
    })

    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'criteria')

    // Verify the criterion exists
    await expect(page.getByText('This criterion will be deleted')).toBeVisible()
    await expect(page.getByText('I1')).toBeVisible()

    // Click delete button
    await page.getByRole('button', { name: /delete/i }).first().click()

    // Confirm deletion in the dialog
    // The delete button in the dialog should be the last one (after the cancel button)
    const deleteButtons = page.getByRole('button', { name: /delete/i })
    await deleteButtons.last().click()

    // Assert the criterion is removed from the list
    await expect(page.getByText('This criterion will be deleted')).not.toBeVisible()

    // Should show empty state again
    await expect(page.getByRole('button', { name: /add criterion/i })).toBeVisible()
  })

  test('should show criteria seeded via API', async ({ page, pageHelper, testUser, api }) => {
    const project = await api.createProject(testUser.token)

    // Create multiple criteria via API
    await api.createCriterion(testUser.token, project.id, {
      type: 'inclusion',
      code: 'I1',
      description: 'First inclusion criterion',
      rationale: 'Rationale for I1',
    })
    await api.createCriterion(testUser.token, project.id, {
      type: 'inclusion',
      code: 'I2',
      description: 'Second inclusion criterion',
      rationale: 'Rationale for I2',
    })
    await api.createCriterion(testUser.token, project.id, {
      type: 'exclusion',
      code: 'E1',
      description: 'First exclusion criterion',
      rationale: 'Rationale for E1',
    })
    await api.createCriterion(testUser.token, project.id, {
      type: 'exclusion',
      code: 'E2',
      description: 'Second exclusion criterion',
      rationale: 'Rationale for E2',
    })

    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'criteria')

    // Assert all criterion codes are visible
    await expect(page.getByText('I1')).toBeVisible()
    await expect(page.getByText('I2')).toBeVisible()
    await expect(page.getByText('E1')).toBeVisible()
    await expect(page.getByText('E2')).toBeVisible()

    // Assert all descriptions are visible
    await expect(page.getByText('First inclusion criterion')).toBeVisible()
    await expect(page.getByText('Second inclusion criterion')).toBeVisible()
    await expect(page.getByText('First exclusion criterion')).toBeVisible()
    await expect(page.getByText('Second exclusion criterion')).toBeVisible()
  })

  test('should show both inclusion and exclusion criteria in separate columns', async ({ page, pageHelper, testUser, api }) => {
    const project = await api.createProject(testUser.token)

    // Create a mix of inclusion and exclusion criteria
    await api.createCriterion(testUser.token, project.id, {
      type: 'inclusion',
      code: 'I1',
      description: 'Include quantitative studies only',
    })
    await api.createCriterion(testUser.token, project.id, {
      type: 'inclusion',
      code: 'I2',
      description: 'Include peer-reviewed publications',
    })
    await api.createCriterion(testUser.token, project.id, {
      type: 'exclusion',
      code: 'E1',
      description: 'Exclude animal studies',
    })
    await api.createCriterion(testUser.token, project.id, {
      type: 'exclusion',
      code: 'E2',
      description: 'Exclude non-English publications',
    })

    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'criteria')

    // Locate the inclusion criteria column (left side, green)
    const inclusionColumn = page.locator('div').filter({ hasText: /^Inclusion Criteria/ }).first()

    // Locate the exclusion criteria column (right side, red)
    const exclusionColumn = page.locator('div').filter({ hasText: /^Exclusion Criteria/ }).first()

    // Assert inclusion criteria are in the inclusion column
    await expect(inclusionColumn.getByText('I1')).toBeVisible()
    await expect(inclusionColumn.getByText('Include quantitative studies only')).toBeVisible()
    await expect(inclusionColumn.getByText('I2')).toBeVisible()
    await expect(inclusionColumn.getByText('Include peer-reviewed publications')).toBeVisible()

    // Assert exclusion criteria are in the exclusion column
    await expect(exclusionColumn.getByText('E1')).toBeVisible()
    await expect(exclusionColumn.getByText('Exclude animal studies')).toBeVisible()
    await expect(exclusionColumn.getByText('E2')).toBeVisible()
    await expect(exclusionColumn.getByText('Exclude non-English publications')).toBeVisible()

    // Verify separation: inclusion column should NOT contain exclusion criteria
    await expect(inclusionColumn.getByText('E1')).not.toBeVisible()
    await expect(inclusionColumn.getByText('E2')).not.toBeVisible()

    // Verify separation: exclusion column should NOT contain inclusion criteria
    await expect(exclusionColumn.getByText('I1')).not.toBeVisible()
    await expect(exclusionColumn.getByText('I2')).not.toBeVisible()
  })
})
