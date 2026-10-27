import { test, expect } from './fixtures'

test.describe('Criteria Management', () => {
  test('should show empty state for project with no criteria', async ({ page, pageHelper, testUser, api }) => {
    const project = await api.createProject(testUser.token)
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'criteria')

    // Both columns should show an empty state with their own "Add ... Criterion" button
    await expect(page.getByRole('button', { name: 'Add Inclusion Criterion' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Add Exclusion Criterion' })).toBeVisible()
    await expect(page.getByTestId('criterion-card')).toHaveCount(0)

    // Verify column titles are present
    await expect(page.getByRole('heading', { name: 'Inclusion Criteria' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Exclusion Criteria' })).toBeVisible()
  })

  test('should create an inclusion criterion', async ({ page, pageHelper, testUser, api }) => {
    const project = await api.createProject(testUser.token)
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'criteria')

    // Click "Add" button in inclusion criteria section
    // Find the section containing "Inclusion Criteria" heading
    await page.getByTestId('add-inclusion').click()

    // Fill the criterion form
    await page.locator('#code').fill('I1')
    await page.locator('#description').fill('Studies must include quantitative data')
    await page.locator('#rationale').fill('We need measurable outcomes for meta-analysis')

    // Submit the form
    await page.getByRole('button', { name: 'Add Criterion', exact: true }).click()

    // Assert the criterion card appears with correct data, in the inclusion column
    const inclusion = page.getByTestId('inclusion-column')
    await expect(inclusion.getByText('I1', { exact: true })).toBeVisible()
    await expect(inclusion.getByText('Studies must include quantitative data')).toBeVisible()
    await expect(inclusion.getByText('We need measurable outcomes for meta-analysis')).toBeVisible()
    await expect(page.getByTestId('exclusion-column').getByTestId('criterion-card')).toHaveCount(0)
  })

  test('should create an exclusion criterion', async ({ page, pageHelper, testUser, api }) => {
    const project = await api.createProject(testUser.token)
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'criteria')

    // Click "Add" button in exclusion criteria section
    await page.getByTestId('add-exclusion').click()

    // Fill the criterion form (no rationale this time)
    await page.locator('#code').fill('E1')
    await page.locator('#description').fill('Animal studies must be excluded')

    // Submit the form
    await page.getByRole('button', { name: 'Add Criterion', exact: true }).click()

    // Assert the criterion card appears in the exclusion column
    const exclusion = page.getByTestId('exclusion-column')
    await expect(exclusion.getByText('E1', { exact: true })).toBeVisible()
    await expect(exclusion.getByText('Animal studies must be excluded')).toBeVisible()
    await expect(page.getByTestId('inclusion-column').getByTestId('criterion-card')).toHaveCount(0)
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
    await page.getByRole('button', { name: 'Edit', exact: true }).click()

    // Change the description
    await page.locator('#description').clear()
    await page.locator('#description').fill('Updated description text')

    // Save the changes
    await page.getByRole('button', { name: 'Update Criterion' }).click()

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
    await expect(page.getByText('I1', { exact: true })).toBeVisible()

    // Click delete on the criterion card
    await page.getByTestId('criterion-card').getByRole('button', { name: 'Delete' }).click()

    // Confirm deletion in the dialog
    await page.getByRole('dialog', { name: 'Delete Criterion' }).getByRole('button', { name: 'Delete', exact: true }).click()

    // Assert the criterion is removed from the list
    await expect(page.getByText('This criterion will be deleted')).not.toBeVisible()

    // Should show empty state again
    await expect(page.getByRole('button', { name: 'Add Inclusion Criterion' })).toBeVisible()
    await expect(page.getByTestId('criterion-card')).toHaveCount(0)
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
    await expect(page.getByText('I1', { exact: true })).toBeVisible()
    await expect(page.getByText('I2', { exact: true })).toBeVisible()
    await expect(page.getByText('E1', { exact: true })).toBeVisible()
    await expect(page.getByText('E2', { exact: true })).toBeVisible()

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
    const inclusionColumn = page.getByTestId('inclusion-column')

    // Locate the exclusion criteria column (right side, red)
    const exclusionColumn = page.getByTestId('exclusion-column')

    // Assert inclusion criteria are in the inclusion column
    await expect(inclusionColumn.getByText('I1', { exact: true })).toBeVisible()
    await expect(inclusionColumn.getByText('Include quantitative studies only')).toBeVisible()
    await expect(inclusionColumn.getByText('I2', { exact: true })).toBeVisible()
    await expect(inclusionColumn.getByText('Include peer-reviewed publications')).toBeVisible()

    // Assert exclusion criteria are in the exclusion column
    await expect(exclusionColumn.getByText('E1', { exact: true })).toBeVisible()
    await expect(exclusionColumn.getByText('Exclude animal studies')).toBeVisible()
    await expect(exclusionColumn.getByText('E2', { exact: true })).toBeVisible()
    await expect(exclusionColumn.getByText('Exclude non-English publications')).toBeVisible()

    // Verify separation: inclusion column should NOT contain exclusion criteria
    await expect(inclusionColumn.getByText('E1', { exact: true })).not.toBeVisible()
    await expect(inclusionColumn.getByText('E2', { exact: true })).not.toBeVisible()

    // Verify separation: exclusion column should NOT contain inclusion criteria
    await expect(exclusionColumn.getByText('I1', { exact: true })).not.toBeVisible()
    await expect(exclusionColumn.getByText('I2', { exact: true })).not.toBeVisible()
  })
})
