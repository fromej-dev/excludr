import { test, expect, generateRisContent, type TestUser } from './fixtures'
import type { Page, Request } from '@playwright/test'

const RUN_AI = '**/api/v1/projects/*/screening/run-ai*'

/** Collect the run-ai requests the page sends. */
function trackRunAi(page: Page): Request[] {
  const seen: Request[] = []
  page.on('request', (req) => {
    if (req.method() === 'POST' && /\/screening\/run-ai(\?|$)/.test(req.url())) seen.push(req)
  })
  return seen
}

/** Pretend the AI is configured: queue whatever is asked for (no websocket result follows). */
async function mockRunAi(page: Page) {
  await page.route(RUN_AI, async (route) => {
    const body = route.request().postDataJSON() as { article_ids?: number[] } | null
    const ids = body?.article_ids ?? []
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ message: 'AI screening started', article_count: ids.length, article_ids: ids }),
    })
  })
}

const idsOf = (req: Request) => (req.postDataJSON() as { article_ids: number[] }).article_ids

test.describe('AI screening lookahead', () => {
  let projectId: number
  let articleIds: number[]
  let user: TestUser

  test.beforeEach(async ({ api, testUser }) => {
    user = testUser
    const project = await api.createProject(testUser.token)
    projectId = project.id
    await api.createCriterion(testUser.token, projectId, {
      type: 'inclusion',
      code: 'I1',
      description: 'Randomized controlled trials',
    })
    await api.uploadRisFile(testUser.token, projectId, generateRisContent(5))
    const { data } = await api.getArticles(testUser.token, projectId)
    articleIds = data.map((a) => a.id).sort((a, b) => a - b)
    expect(articleIds).toHaveLength(5)
  })

  test('queues the current and next two articles, then only the newly needed one', async ({
    page,
    pageHelper,
  }) => {
    await mockRunAi(page)
    const requests = trackRunAi(page)
    await pageHelper.loginDirect(user.token)
    await pageHelper.goToProjectTab(projectId, 'screening')
    await page.getByTestId('article-title').waitFor()

    await expect.poll(() => requests.length).toBe(1)
    expect(idsOf(requests[0])).toEqual(articleIds.slice(0, 3))
    // The current article was queued: its verdict shows as in progress
    await expect(page.getByTestId('ai-pending')).toContainText('AI screening…')
    await expect(page.getByTestId('ai-auto-ahead')).toBeChecked()

    const firstTitle = (await page.getByTestId('article-title').textContent())!.trim()
    await page.getByRole('button', { name: 'Include (I)' }).click()
    await expect(page.getByTestId('article-title')).not.toHaveText(firstTitle)

    await expect.poll(() => requests.length).toBe(2)
    expect(idsOf(requests[1])).toEqual([articleIds[3]])

    // Skipping ahead without deciding needs just the next one again
    const secondTitle = (await page.getByTestId('article-title').textContent())!.trim()
    await page.getByRole('button', { name: 'Next (N)' }).click()
    await expect(page.getByTestId('article-title')).not.toHaveText(secondTitle)
    await expect.poll(() => requests.length).toBe(3)
    expect(idsOf(requests[2])).toEqual([articleIds[4]])

    // Going back sends nothing: everything around it was requested already
    await page.getByRole('button', { name: 'Previous (P)' }).click()
    await page.waitForTimeout(500)
    expect(requests).toHaveLength(3)
  })

  test('shows a quiet note when AI is not configured and keeps working', async ({ page, pageHelper }) => {
    // The e2e backend has no Anthropic key: run-ai answers 503
    const requests = trackRunAi(page)
    await pageHelper.loginDirect(user.token)
    await pageHelper.goToProjectTab(projectId, 'screening')
    await page.getByTestId('article-title').waitFor()

    await expect(page.getByTestId('ai-unavailable')).toContainText('AI screening unavailable')
    await expect(page.getByText('No AI screening result yet.')).toBeVisible()
    expect(requests).toHaveLength(1)

    const firstTitle = (await page.getByTestId('article-title').textContent())!.trim()
    await page.getByRole('button', { name: 'Include (I)' }).click()
    await expect(page.getByRole('alert').filter({ hasText: 'Included:' })).toBeVisible()
    await expect(page.getByTestId('article-title')).not.toHaveText(firstTitle)

    // Stopped trying after the 503, and no error toast about it
    await page.waitForTimeout(500)
    expect(requests).toHaveLength(1)
    await expect(page.getByRole('alert').filter({ hasText: /AI screening|not configured/i })).toHaveCount(0)
    // The manual button is still offered
    await expect(page.getByRole('button', { name: 'Screen with AI' })).toBeVisible()
  })

  test('sends nothing while "Auto-screen ahead" is off', async ({ page, pageHelper }) => {
    await mockRunAi(page)
    const requests = trackRunAi(page)
    await pageHelper.loginDirect(user.token)
    await page.evaluate(() => localStorage.setItem('excludr_ai_lookahead', '0'))
    await pageHelper.goToProjectTab(projectId, 'screening')
    await page.getByTestId('article-title').waitFor()

    const toggle = page.getByTestId('ai-auto-ahead')
    await expect(toggle).not.toBeChecked()
    const firstTitle = (await page.getByTestId('article-title').textContent())!.trim()
    await page.getByRole('button', { name: 'Next (N)' }).click()
    await expect(page.getByTestId('article-title')).not.toHaveText(firstTitle)
    await page.waitForTimeout(500)
    expect(requests).toHaveLength(0)

    // Switching it back on starts the lookahead and is remembered
    await page.getByLabel('Auto-screen ahead').check()
    await expect.poll(() => requests.length).toBe(1)
    expect(await page.evaluate(() => localStorage.getItem('excludr_ai_lookahead'))).toBe('1')
  })

  test('phone: the Note toggle in the action bar saves a note with the decision', async ({
    page,
    pageHelper,
    request,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await pageHelper.loginDirect(user.token)
    await pageHelper.goToProjectTab(projectId, 'screening')
    await page.getByTestId('article-title').waitFor()
    const firstTitle = (await page.getByTestId('article-title').textContent())!.trim()

    const bar = page.getByTestId('mobile-action-bar')
    const toggle = bar.getByRole('button', { name: 'Note' })
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await expect(bar.getByLabel('Note (optional)')).toHaveCount(0)

    await toggle.click()
    const note = bar.getByLabel('Note (optional)')
    await expect(note).toBeVisible()
    await expect(note).toBeFocused()
    await expect(note).toBeInViewport()
    await note.fill('Wrong population, checked on phone')
    await bar.getByRole('button', { name: 'Exclude' }).click()

    await expect(page.getByRole('alert').filter({ hasText: 'Excluded:' })).toBeVisible()
    await expect(page.getByTestId('article-title')).not.toHaveText(firstTitle)
    // Fresh article: the note is cleared and folded away again
    await expect(bar.getByLabel('Note (optional)')).toHaveCount(0)
    await bar.getByRole('button', { name: 'Note' }).click()
    await expect(bar.getByLabel('Note (optional)')).toHaveValue('')

    const res = await request.get(
      `/api/v1/projects/${projectId}/screening/articles/${articleIds[0]}/decisions`,
      { headers: { Authorization: `Bearer ${user.token}` } }
    )
    expect(res.ok()).toBeTruthy()
    const decisions = (await res.json()).data as Array<{ source: string; decision: string; reasoning: string | null }>
    const mine = decisions.find((d) => d.source === 'human')
    expect(mine?.decision).toBe('exclude')
    expect(mine?.reasoning).toBe('Wrong population, checked on phone')
  })

  test('desktop: the mobile Note controls are not displayed', async ({ page, pageHelper }) => {
    await pageHelper.loginDirect(user.token)
    await pageHelper.goToProjectTab(projectId, 'screening')
    await page.getByTestId('article-title').waitFor()
    await expect(page.getByRole('button', { name: 'Note' })).toHaveCount(0)
    await expect(page.locator('#reasoning')).toBeVisible()
  })
})
