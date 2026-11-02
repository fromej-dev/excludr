import type { Page } from '@playwright/test'
import { test, expect, generateRisContent, type ApiHelper, type TestUser } from './fixtures'

const auth = (token: string) => ({ Authorization: `Bearer ${token}` })

interface Setup {
  projectId: number
  articleIds: number[]
}

/** A project with one criterion and `n` records, optionally prioritized with a stopping rule. */
async function setup(
  api: ApiHelper,
  owner: TestUser,
  n: number,
  settings?: Record<string, unknown>,
): Promise<Setup> {
  const project = await api.createProject(owner.token)
  await api.createCriterion(owner.token, project.id, { type: 'inclusion', code: 'I1', description: 'Randomized trials' })
  await api.uploadRisFile(owner.token, project.id, generateRisContent(n))
  if (settings) {
    await api.updateProject(owner.token, project.id, { prioritized_screening: true, ...settings })
    // Decisions in the same wall-clock second as the switch-on may not count on SQLite
    await new Promise((resolve) => setTimeout(resolve, 1100))
  }
  const articles = await api.getArticles(owner.token, project.id)
  return { projectId: project.id, articleIds: articles.data.map((a) => a.id).sort((a, b) => a - b) }
}

const toast = (page: Page, text: string) => page.getByRole('alert').filter({ hasText: text })

test.describe('Prioritized screening and the stopping rule', () => {
  test('owner turns on prioritized screening and sets the stopping rule', async ({
    page,
    pageHelper,
    api,
    testUser,
    request,
  }) => {
    const { projectId } = await setup(api, testUser, 3)
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'overview')

    await page.getByTestId('prioritized-toggle').check()
    await expect(toast(page, 'Prioritized screening on')).toBeVisible()
    await page.getByTestId('stop-threshold').fill('50')
    await page.getByTestId('ranking-min-random').fill('10')
    await page.getByTestId('prioritization-save').click()
    await expect(toast(page, 'Screening rule saved')).toBeVisible()

    await page.reload()
    await expect(page.getByTestId('stop-threshold')).toHaveValue('50')
    await expect(page.getByTestId('ranking-min-random')).toHaveValue('10')
    await expect(page.getByTestId('protocol-note')).toBeVisible()
    const project = await (await request.get(`/api/v1/projects/${projectId}`, { headers: auth(testUser.token) })).json()
    expect(project.stop_after_consecutive_excludes).toBe(50)
    expect(project.ranking_min_random).toBe(10)

    await page.getByTestId('stopping-rule-toggle').uncheck()
    await page.getByTestId('prioritization-save').click()
    await expect(page.getByTestId('prioritization-save')).toBeDisabled()
    await expect
      .poll(async () => {
        const p = await (await request.get(`/api/v1/projects/${projectId}`, { headers: auth(testUser.token) })).json()
        return p.stop_after_consecutive_excludes
      })
      .toBeNull()

    await page.getByTestId('stopping-rule-toggle').check()
    await page.getByTestId('stop-threshold').fill('0')
    await expect(page.getByTestId('prioritization-save')).toBeDisabled()
    await expect(page.getByRole('alert').filter({ hasText: 'whole number from 1' })).toBeVisible()
  })

  test('reviewers and viewers see screening settings read-only', async ({ page, pageHelper, api, testUser }) => {
    const { projectId } = await setup(api, testUser, 2, { stop_after_consecutive_excludes: 5 })
    for (const role of ['reviewer', 'viewer'] as const) {
      const member = await api.addMember(testUser.token, projectId, role)
      await pageHelper.loginDirect(member.token)
      await pageHelper.goToProjectTab(projectId, 'overview')
      await expect(page.getByTestId('prioritized-toggle')).toBeDisabled()
      await expect(page.getByTestId('prioritization-settings').getByText('Only the owner can change this.')).toBeVisible()
      await expect(page.getByTestId('rerank-button')).toHaveCount(0)
      await expect(page.getByTestId('apply-rule-open')).toHaveCount(0)
      await expect(page.getByTestId('ranking-status')).toBeVisible()
    }
  })

  test('owner re-ranks and sees the last ranking', async ({ page, pageHelper, api, testUser }) => {
    const { projectId } = await setup(api, testUser, 3, { stop_after_consecutive_excludes: 5 })
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'overview')
    const button = page.getByTestId('rerank-button')
    await expect(button).toHaveText('Re-rank now')
    await button.click()
    await expect(button).toHaveText('Re-rank now')
    await expect(page.getByTestId('ranking-last-run')).toContainText('Last ranked')
    await expect(page.getByTestId('ranking-last-run')).toContainText('cold start')
  })

  test('screening shows the ranked badge and the exclude streak', async ({ page, pageHelper, api, testUser }) => {
    const { projectId } = await setup(api, testUser, 5, { stop_after_consecutive_excludes: 3 })
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'screening')
    await expect(page.getByTestId('queue-badge')).toHaveText('Ranked by relevance')
    await expect(page.getByTestId('stopping-streak')).toContainText('0 / 3 consecutive excludes')
    await expect(page.getByTestId('article-title')).toBeVisible()
    const title = page.getByTestId('article-title')
    let seen = await title.innerText()
    await page.keyboard.press('e')
    await expect(page.getByTestId('stopping-streak')).toContainText('1 / 3 consecutive excludes')
    await expect(title).not.toHaveText(seen)
    seen = await title.innerText()
    await page.keyboard.press('e')
    await expect(page.getByTestId('stopping-streak')).toContainText('2 / 3 consecutive excludes')
    await expect(title).not.toHaveText(seen)
    await page.keyboard.press('i')
    await expect(page.getByTestId('stopping-streak')).toContainText('0 / 3 consecutive excludes')
  })

  test('random start badge counts down', async ({ page, pageHelper, api, testUser }) => {
    const { projectId } = await setup(api, testUser, 5, { ranking_min_random: 2 })
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'screening')
    await expect(page.getByTestId('queue-badge')).toContainText('Random start · 2 to go')
    await page.keyboard.press('e')
    await expect(page.getByTestId('queue-badge')).toContainText('Random start · 1 to go')
    await page.keyboard.press('e')
    await expect(page.getByTestId('queue-badge')).toContainText('Ranked by relevance')
  })

  /** Owner (and optionally a reviewer) in a project where the rule is met: 2 excluded, rest open. */
  async function metProject(api: ApiHelper, owner: TestUser, n = 5, threshold = 2): Promise<Setup> {
    const s = await setup(api, owner, n, { stop_after_consecutive_excludes: threshold })
    for (const id of s.articleIds.slice(0, threshold)) await api.decide(owner.token, s.projectId, id, 'exclude')
    return s
  }

  test('owner applies the stopping rule when it is met', async ({ page, pageHelper, api, testUser }) => {
    const { projectId } = await metProject(api, testUser)
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'screening')
    await expect(page.getByTestId('stopping-rule-met')).toBeVisible()
    await page.getByTestId('apply-rule-open').click()
    await expect(page.getByTestId('apply-rule-closable')).toContainText('3')
    await expect(page.getByTestId('apply-rule-left-open')).toHaveCount(0)
    await expect(page.getByTestId('apply-rule-confirm')).toHaveText('Close 3 records')
    await page.getByTestId('apply-rule-confirm').click()

    await expect(toast(page, 'Stopping rule applied: 3 records closed')).toHaveCount(1)
    await expect(page.getByTestId('stopped-empty')).toBeVisible()

    await pageHelper.goToProjectTab(projectId, 'overview')
    await expect(page.getByTestId('progress-not-screened')).toContainText('3')
    await expect(page.getByTestId('progress-outcome-note')).toContainText('3 not screened (stopping rule)')
    await expect(page.getByTestId('progress-outcome-note')).not.toContainText('still open')

    await page.goto(`/projects/${projectId}/articles?status=not_screened`)
    await expect(page.getByTestId('article-card')).toHaveCount(3)
    for (const status of await page.getByTestId('article-status').all()) {
      await expect(status).toHaveText('Not screened (stopping rule)')
    }
    await page.goto(`/projects/${projectId}/articles?status=excluded`)
    await expect(page.getByTestId('article-card')).toHaveCount(2)

    await page.goto(`/projects/${projectId}/reports`)
    await expect(page.getByTestId('prisma-automation')).toContainText('3')
    await expect(page.getByTestId('prisma-screening-method')).toContainText('The remaining 3 records were not screened')
  })

  test('dual screening leaves started records open', async ({ page, pageHelper, api, testUser }) => {
    const project = await api.createProject(testUser.token)
    await api.createCriterion(testUser.token, project.id, { type: 'inclusion', code: 'I1', description: 'Trials' })
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(4))
    await api.updateProject(testUser.token, project.id, { required_reviewers: 2 })
    await api.updateProject(testUser.token, project.id, { prioritized_screening: true, stop_after_consecutive_excludes: 1 })
    await new Promise((resolve) => setTimeout(resolve, 1100))
    const reviewer = await api.addMember(testUser.token, project.id, 'reviewer')
    const ids = (await api.getArticles(testUser.token, project.id)).data.map((a) => a.id).sort((a, b) => a - b)

    await api.decide(testUser.token, project.id, ids[0], 'exclude')
    await api.decide(reviewer.token, project.id, ids[0], 'exclude')
    await api.decide(reviewer.token, project.id, ids[1], 'exclude')

    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(project.id, 'screening')
    await page.getByTestId('apply-rule-open').click()
    await expect(page.getByTestId('apply-rule-closable')).toContainText('2')
    await expect(page.getByTestId('apply-rule-left-open')).toContainText('1')
    await page.getByTestId('apply-rule-confirm').click()
    await expect(page.getByTestId('apply-rule-dialog')).toHaveCount(0)

    await page.goto(`/projects/${project.id}/articles?status=screening`)
    await expect(page.getByTestId('article-card')).toHaveCount(1)
    await page.goto(`/projects/${project.id}/articles?status=not_screened`)
    await expect(page.getByTestId('article-card')).toHaveCount(2)
  })

  test('reviewer sees the rule met but cannot apply it', async ({ page, pageHelper, api, testUser }) => {
    const { projectId } = await metProject(api, testUser)
    const reviewer = await api.addMember(testUser.token, projectId, 'reviewer')
    await pageHelper.loginDirect(reviewer.token)
    await pageHelper.goToProjectTab(projectId, 'screening')
    await expect(page.getByTestId('stopping-rule-met')).toContainText('The owner can close the remaining unscreened records')
    await expect(page.getByTestId('apply-rule-open')).toHaveCount(0)
  })

  test('forcing the rule before it is met needs a reason', async ({ page, pageHelper, api, testUser, request }) => {
    const { projectId, articleIds } = await setup(api, testUser, 3, { stop_after_consecutive_excludes: 5 })
    await api.decide(testUser.token, projectId, articleIds[0], 'exclude')
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'overview')
    await page.getByTestId('apply-rule-open').click()
    await expect(page.getByTestId('apply-rule-not-met')).toContainText('not met yet: 1 of 5')
    const confirm = page.getByTestId('apply-rule-confirm')
    await expect(confirm).toBeDisabled()
    await page.getByTestId('apply-rule-reason').fill('   ')
    await expect(confirm).toBeDisabled()
    await page.getByTestId('apply-rule-reason').fill('Time-boxed rapid review')
    await expect(confirm).toHaveText('Close 2 records anyway')
    await confirm.click()
    await expect(toast(page, 'Stopping rule applied: 2 records closed')).toBeVisible()
    const status = await (
      await request.get(`/api/v1/projects/${projectId}/screening/stopping-rule`, { headers: auth(testUser.token) })
    ).json()
    expect(status.not_screened).toBe(2)
  })

  test('apply errors stay in the dialog', async ({ page, pageHelper, api, testUser }) => {
    const { projectId } = await metProject(api, testUser, 3, 1)
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'screening')
    await page.getByTestId('apply-rule-open').click()

    await page.route('**/apply-stopping-rule', (route) =>
      route.fulfill({ status: 402, json: { detail: "This review's pass has expired" } }),
    )
    await page.getByTestId('apply-rule-confirm').click()
    await expect(page.getByTestId('apply-rule-error')).toContainText("This review's pass has expired")
    await expect(page.getByTestId('apply-rule-dialog')).toBeVisible()

    await page.unroute('**/apply-stopping-rule')
    await page.route('**/apply-stopping-rule', (route) =>
      route.fulfill({ status: 409, json: { detail: 'The stopping rule is not met (1 of 2 consecutive excludes)' } }),
    )
    await page.route('**/screening/stopping-rule', async (route) => {
      const res = await route.fetch()
      const body = await res.json()
      await route.fulfill({ json: { ...body, met: false, can_apply: false, threshold: 2, consecutive_excludes: 1 } })
    })
    await page.getByTestId('apply-rule-confirm').click()
    await expect(page.getByTestId('apply-rule-error')).toContainText('not met (1 of 2')
    await expect(page.getByTestId('apply-rule-reason')).toBeVisible()
    await expect(page.getByTestId('apply-rule-dialog')).toBeVisible()
  })

  test('owner reopens not-screened records from Articles', async ({ page, pageHelper, api, testUser, request }) => {
    const { projectId } = await metProject(api, testUser)
    const applied = await request.post(`/api/v1/projects/${projectId}/screening/apply-stopping-rule`, {
      headers: auth(testUser.token),
    })
    expect(applied.ok()).toBeTruthy()

    const reviewer = await api.addMember(testUser.token, projectId, 'reviewer')
    await pageHelper.loginDirect(reviewer.token)
    await pageHelper.goToProjectTab(projectId, 'articles')
    await expect(page.getByTestId('article-card')).toHaveCount(5)
    await expect(page.getByTestId('reopen-not-screened')).toHaveCount(0)

    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'articles')
    const open = page.getByTestId('reopen-not-screened')
    await expect(open).toHaveText('Reopen 3 not-screened records')
    await open.click()
    await expect(page.getByTestId('reopen-dialog')).toBeVisible()
    await page.getByTestId('reopen-confirm').click()
    await expect(toast(page, '3 records reopened for screening')).toBeVisible()
    await expect(open).toHaveCount(0)

    await page.goto(`/projects/${projectId}/articles?status=not_screened`)
    await expect(page.getByTestId('articles-no-matches')).toBeVisible()
    await page.goto(`/projects/${projectId}/articles?status=screening`)
    await expect(page.getByTestId('article-card')).toHaveCount(3)
  })

  test('relevance column sorts most relevant first', async ({ page, pageHelper, api, testUser }) => {
    const prioritized = await setup(api, testUser, 3, { stop_after_consecutive_excludes: 5 })
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(prioritized.projectId, 'articles')
    await expect(page.getByTestId('sort-relevance_score')).toBeVisible()
    await expect(page.getByTestId('relevance-score').first()).toHaveText(/^(\d\.\d\d|—)$/)

    const [first] = await Promise.all([
      page.waitForRequest((r) => r.url().includes('sort_by=relevance_score') && r.url().includes('order=desc')),
      page.getByTestId('sort-relevance_score').click(),
    ])
    expect(first).toBeTruthy()
    await expect(page).toHaveURL(/sort=relevance_score&order=desc/)
    await Promise.all([
      page.waitForRequest((r) => r.url().includes('sort_by=relevance_score') && r.url().includes('order=asc')),
      page.getByTestId('sort-relevance_score').click(),
    ])
    await expect(page).toHaveURL(/sort=relevance_score&order=asc/)

    const plain = await setup(api, testUser, 2)
    await pageHelper.goToProjectTab(plain.projectId, 'articles')
    await expect(page.getByTestId('article-card')).toHaveCount(2)
    await expect(page.getByTestId('sort-relevance_score')).toHaveCount(0)
  })

  test('screening moves on when the open record is closed by the rule', async ({
    page,
    pageHelper,
    api,
    testUser,
    request,
  }) => {
    const { projectId } = await metProject(api, testUser, 4, 2)
    const reviewer = await api.addMember(testUser.token, projectId, 'reviewer')
    await pageHelper.loginDirect(reviewer.token)
    await pageHelper.goToProjectTab(projectId, 'screening')
    await expect(page.getByTestId('article-title')).toBeVisible()

    const applied = await request.post(`/api/v1/projects/${projectId}/screening/apply-stopping-rule`, {
      headers: auth(testUser.token),
    })
    expect(applied.ok()).toBeTruthy()

    await expect(toast(page, 'Stopping rule applied: 2 records closed').first()).toBeVisible()
    await expect(page.getByTestId('stopped-empty')).toBeVisible()
    const decisions: string[] = []
    page.on('request', (r) => r.method() === 'POST' && r.url().includes('/decisions') && decisions.push(r.url()))
    await page.keyboard.press('e')
    await page.waitForTimeout(300)
    expect(decisions).toHaveLength(0)
  })

  test('shortcut keys are ignored while the apply dialog is open', async ({ page, pageHelper, api, testUser }) => {
    const { projectId } = await metProject(api, testUser)
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'screening')
    const decisions: string[] = []
    page.on('request', (r) => r.method() === 'POST' && r.url().includes('/decisions') && decisions.push(r.url()))
    await page.getByTestId('apply-rule-open').click()
    await expect(page.getByTestId('apply-rule-dialog')).toBeVisible()
    await page.keyboard.press('e')
    await page.waitForTimeout(300)
    expect(decisions).toHaveLength(0)
    await expect(page.getByTestId('apply-rule-dialog')).toBeVisible()
  })

  test('progress card does not count not-screened records as open', async ({ page, pageHelper, api, testUser }) => {
    const { projectId } = await setup(api, testUser, 2)
    await page.route(/\/screening\/stats/, async (route) => {
      const body = await (await route.fetch()).json()
      await route.fulfill({
        json: {
          ...body,
          total_articles: 10,
          included: 1,
          excluded: 2,
          excluded_title_abstract: 2,
          excluded_full_text: 0,
          not_screened_stopping_rule: 4,
          title_abstract_total: 10,
          title_abstract_completed: 9,
          full_text_eligible: 3,
          uncertain: 0,
          awaiting_screening: 1,
        },
      })
    })
    await pageHelper.loginDirect(testUser.token)
    await pageHelper.goToProjectTab(projectId, 'overview')
    await expect(page.getByTestId('progress-outcome-note')).toContainText('4 not screened (stopping rule) · 3 still open')
    await expect(page.getByTestId('progress-ta')).toContainText('3 passed · 2 excluded · 4 not screened (stopping rule)')
  })

  test('PRISMA shows automation removals and copies the methods text', async ({
    page,
    context,
    pageHelper,
    api,
    testUser,
  }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write'])
    const { projectId } = await setup(api, testUser, 2)
    const sentence = 'Title and abstract screening was prioritized by a relevance model.'
    let override: { auto: number; method: string | null } = { auto: 4, method: sentence }
    await page.route(/\/prisma$/, async (route) => {
      const body = await (await route.fetch()).json()
      await route.fulfill({
        json: {
          ...body,
          identification: {
            ...body.identification,
            duplicates_removed: override.auto > 0 ? 2 : body.identification.duplicates_removed,
            marked_ineligible_by_automation: override.auto,
          },
          screening_method: override.method,
        },
      })
    })
    await pageHelper.loginDirect(testUser.token)
    await page.goto(`/projects/${projectId}/reports`)
    await expect(page.getByTestId('prisma-diagram')).toContainText('Records removed before screening (n = 6)')
    await expect(page.getByTestId('prisma-duplicates')).toContainText('2')
    await expect(page.getByTestId('prisma-automation')).toContainText('4')
    await page.getByTestId('copy-screening-method').click()
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(sentence)

    override = { auto: 0, method: null }
    await page.reload()
    await expect(page.getByTestId('prisma-diagram')).toBeVisible()
    await expect(page.getByTestId('screening-method')).toHaveCount(0)
    await expect(page.getByTestId('prisma-automation')).toHaveCount(0)
  })
})
