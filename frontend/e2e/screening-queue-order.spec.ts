import { test, expect, generateRisContent } from './fixtures'
import type { Page, Request } from '@playwright/test'

/** Serve `pending_for_me` article lists in a fixed queue order, two ids per page. */
async function mockQueue(page: Page, order: number[]) {
  const perPage = 2
  await page.route('**/api/v1/projects/*/articles?*', async (route) => {
    const url = new URL(route.request().url())
    if (url.searchParams.get('pending_for_me') !== 'true') return route.continue()
    const p = Number(url.searchParams.get('page') ?? '1')
    await route.fulfill({
      json: {
        data: order.slice((p - 1) * perPage, p * perPage).map((id) => ({ id })),
        meta: {
          pagination: {
            total_items: order.length,
            per_page: perPage,
            current_page: p,
            total_pages: Math.ceil(order.length / perPage),
          },
        },
        links: {},
      },
    })
  })
}

/** `/screening/next` serves the given article. */
async function mockNext(page: Page, articleId: number) {
  await page.route('**/api/v1/projects/*/screening/next*', async (route) => {
    const res = await route.fetch({ url: route.request().url().replace(/\/screening\/next.*$/, `/articles/${articleId}`) })
    await route.fulfill({
      json: { article: await res.json(), queue_order: 'ranked', random_start_remaining: 0 },
    })
  })
}

async function mockRunAi(page: Page): Promise<Request[]> {
  const seen: Request[] = []
  await page.route('**/api/v1/projects/*/screening/run-ai*', async (route) => {
    seen.push(route.request())
    const ids = (route.request().postDataJSON() as { article_ids?: number[] } | null)?.article_ids ?? []
    await route.fulfill({
      json: { message: 'AI screening started', article_count: ids.length, article_ids: ids },
    })
  })
  return seen
}

test.describe('Screening queue order', () => {
  let projectId: number
  let ids: number[]
  let titles: Record<number, string>
  let token: string

  test.beforeEach(async ({ api, testUser }) => {
    token = testUser.token
    const project = await api.createProject(token)
    projectId = project.id
    await api.createCriterion(token, projectId, { type: 'inclusion', code: 'I1', description: 'Randomized controlled trials' })
    await api.uploadRisFile(token, projectId, generateRisContent(5))
    const { data } = await api.getArticles(token, projectId)
    ids = data.map((a) => a.id).sort((a, b) => a - b)
    titles = Object.fromEntries(data.map((a) => [a.id, a.title]))
    expect(ids).toHaveLength(5)
  })

  const open = async (page: Page, pageHelper: { loginDirect(t: string): Promise<void>; goToProjectTab(id: number, tab: string): Promise<void> }) => {
    await pageHelper.loginDirect(token)
    await pageHelper.goToProjectTab(projectId, 'screening')
    await page.getByTestId('article-title').waitFor()
  }
  const shows = (page: Page, id: number) =>
    expect(page.getByTestId('article-title')).toHaveText(titles[id])

  test('Next follows the server queue order across pages', async ({ page, pageHelper }) => {
    const [a0, a1, a2, a3, a4] = ids
    await mockQueue(page, [a3, a1, a4, a0, a2])
    await mockNext(page, a3)
    await open(page, pageHelper)
    await shows(page, a3)
    for (const id of [a1, a4, a0, a2]) {
      await page.getByRole('button', { name: 'Next (N)' }).click()
      await shows(page, id)
    }
    await page.getByRole('button', { name: 'Next (N)' }).click()
    await expect(page.getByRole('alert').filter({ hasText: 'No other articles in the queue' })).toBeVisible()
  })

  test('lookahead queues the next two in queue order', async ({ page, pageHelper }) => {
    const [a0, a1, a2, a3, a4] = ids
    const requests = await mockRunAi(page)
    await mockQueue(page, [a3, a1, a4, a0, a2])
    await mockNext(page, a3)
    await open(page, pageHelper)
    await expect.poll(() => requests.length).toBe(1)
    expect((requests[0].postDataJSON() as { article_ids: number[] }).article_ids).toEqual([a3, a1, a4])
  })

  test('Next from an article not in the queue goes to the top unseen article', async ({ page, pageHelper }) => {
    const [a0, a1, a2, a3] = ids
    await mockQueue(page, [a1, a2, a3])
    await mockNext(page, a0)
    await open(page, pageHelper)
    await shows(page, a0)
    await page.getByRole('button', { name: 'Next (N)' }).click()
    await shows(page, a1)
  })

  test('Next wraps around to unseen articles before the current one', async ({ page, pageHelper }) => {
    const [a0, a1, a2] = ids
    await mockQueue(page, [a0, a1, a2])
    await mockNext(page, a2)
    await open(page, pageHelper)
    await shows(page, a2)
    await page.getByRole('button', { name: 'Next (N)' }).click()
    await shows(page, a0)
  })
})
