import type { WebSocketRoute } from '@playwright/test'
import { test, expect, generateRisContent } from './fixtures'

/**
 * Live stats while bulk jobs run. A real full-text batch would hit Unpaywall/PMC, so the websocket is
 * proxied with page.routeWebSocket (real server traffic still flows) and the test injects the batch
 * events the backend would send, while the stats endpoint returns controlled numbers.
 */
test.describe('Live progress during bulk jobs', () => {
  test('stats refresh on batch events, throttled, ignoring other projects', async ({
    page,
    pageHelper,
    testUser,
    api,
  }) => {
    const project = await api.createProject(testUser.token)
    await api.createCriterion(testUser.token, project.id, { type: 'inclusion', code: 'I1', description: 'RCTs' })
    await api.uploadRisFile(testUser.token, project.id, generateRisContent(3))

    // Proxy the app's websocket so the test can push server messages into it
    let socket: WebSocketRoute | null = null
    await page.routeWebSocket(/\/api\/v1\/ws/, (ws) => {
      ws.connectToServer()
      socket = ws
    })
    const push = (projectId: number, data: Record<string, unknown>) =>
      socket!.send(
        JSON.stringify({
          type: 'room_message',
          message: `event ${String(data.type)}`,
          room: `project_${projectId}`,
          data: { level: 'info', notification: true, project_id: projectId, ...data },
        })
      )

    // Stats come from the real backend, overlaid with the numbers a running batch would produce
    let overlay: Record<string, number> = {}
    let statsCalls = 0
    await page.route(/\/screening\/stats/, async (route) => {
      statsCalls++
      const res = await route.fetch()
      const body = await res.json()
      const data = { ...(body.data ?? body), ...overlay }
      await route.fulfill({ response: res, json: body.data ? { ...body, data } : data })
    })

    await pageHelper.loginDirect(testUser.token)
    socket = null // the next page load opens a new socket
    await pageHelper.goToProjectTab(project.id, 'overview')
    const retrieved = page.getByTestId('progress-ft-retrieved')
    await expect(retrieved).toContainText('0 / 0')
    await expect.poll(() => socket !== null).toBe(true)

    const progress = (n: number) => ({ type: 'fulltext_progress', retrieved: n, errors: 0, total: 3 })
    overlay = {
      title_abstract_completed: 3,
      full_text_eligible: 3,
      full_text_retrieved: 1,
      awaiting_full_text: 2,
      awaiting_screening: 0,
    }

    // Another project's events are ignored
    let before = statsCalls
    push(project.id + 100000, progress(1))
    await page.waitForTimeout(500)
    expect(statsCalls).toBe(before)
    await expect(retrieved).toContainText('0 / 0')

    // A burst of progress events: one immediate refresh, then one trailing refresh at most
    before = statsCalls
    for (let i = 0; i < 5; i++) push(project.id, progress(1))
    await expect(retrieved).toContainText('1 / 3')
    await expect(retrieved).toContainText('2 awaiting retrieval')
    await page.waitForTimeout(2000)
    expect(statsCalls - before).toBeGreaterThanOrEqual(1)
    expect(statsCalls - before).toBeLessThanOrEqual(2)

    // A change inside the throttle window still lands (trailing call)
    overlay = { ...overlay, full_text_retrieved: 1 }
    push(project.id, progress(1))
    overlay = { ...overlay, full_text_retrieved: 2, awaiting_full_text: 1 }
    push(project.id, progress(2))
    await expect(retrieved).toContainText('2 / 3', { timeout: 5000 })

    // Completion refreshes once more, right away
    overlay = { ...overlay, full_text_retrieved: 3, awaiting_full_text: 0 }
    push(project.id, { type: 'fulltext_complete', retrieved: 3, errors: 0, total: 3 })
    await expect(retrieved).toContainText('3 / 3', { timeout: 1000 })
    await expect(retrieved).not.toContainText('awaiting retrieval')

    // The screening toolbar uses the same live stats (AI batch events)
    await page.getByRole('link', { name: /^Full text/ }).first().click()
    await expect(page.getByTestId('screening-progress')).toContainText('0 / 3 screened')
    overlay = { ...overlay, full_text_completed: 1, included: 1 }
    push(project.id, { type: 'ai_screening_progress', screened: 1, errors: 0, total: 3 })
    await expect(page.getByTestId('screening-progress')).toContainText('1 / 3 screened')
  })

  test('sidebar Title/abstract count follows the server when a batch completes', async ({
    page,
    pageHelper,
    testUser,
    api,
    request,
  }) => {
    const token = testUser.token
    const project = await api.createProject(token)
    await api.createCriterion(token, project.id, { type: 'inclusion', code: 'I1', description: 'RCTs' })
    await api.uploadRisFile(token, project.id, generateRisContent(3))
    const { data } = await api.getArticles(token, project.id)

    let socket: WebSocketRoute | null = null
    await page.routeWebSocket(/\/api\/v1\/ws/, (ws) => {
      ws.connectToServer()
      socket = ws
    })
    const push = (payload: Record<string, unknown>) =>
      socket!.send(
        JSON.stringify({
          type: 'room_message',
          message: `event ${String(payload.type)}`,
          room: `project_${project.id}`,
          data: { level: 'info', notification: true, project_id: project.id, ...payload },
        })
      )

    await pageHelper.loginDirect(token)
    socket = null
    await pageHelper.goToProjectTab(project.id, 'overview')
    const count = page.getByTestId('nav-count-title_abstract')
    await expect(count).toHaveText('3')
    await expect.poll(() => socket !== null).toBe(true)

    // Server state changes behind the UI's back: one article is excluded, one included
    for (const [i, decision] of (['exclude', 'include'] as const).entries()) {
      const res = await request.post(`/api/v1/projects/${project.id}/screening/articles/${data[i].id}/decisions`, {
        headers: { Authorization: `Bearer ${token}` },
        data: { stage: 'title_abstract', decision, source: 'human', reasoning: 'e2e' },
      })
      expect(res.status()).toBe(201)
    }
    await page.waitForTimeout(500)
    await expect(count).toHaveText('3') // no event yet, no refresh

    push({ type: 'ai_screening_complete', screened: 2, errors: 0, total: 3 })
    await expect(count).toHaveText('1', { timeout: 3000 })
  })
})
