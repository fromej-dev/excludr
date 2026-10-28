import { mkdirSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { test, expect, type APIRequestContext, type Browser, type Page } from '@playwright/test'
import {
  articles,
  criteria,
  heroTitle,
  owner,
  project,
  reviewer,
  type AiVerdict,
  type DemoArticle,
  type Vote,
} from './demo-data'

/**
 * Seeds the fictional demo review and captures the homepage screenshots.
 * Run with `npm run screenshots` (see playwright.screenshots.config.ts).
 */

const API = '/api/v1'
const OUT_DIR = fileURLToPath(new URL('../src/assets/screenshots/', import.meta.url))
const VIEWPORT = { width: 1440, height: 900 }
const THEMES = ['light', 'dark'] as const
type Theme = (typeof THEMES)[number]

type Stage = 'title_abstract' | 'full_text'

class Seeder {
  constructor(
    private request: APIRequestContext,
    readonly token: string
  ) {}

  private headers() {
    return { Authorization: `Bearer ${this.token}` }
  }

  async post<T = unknown>(path: string, data?: object): Promise<T> {
    const res = await this.request.post(`${API}${path}`, { headers: this.headers(), data })
    expect(res.ok(), `POST ${path}: ${res.status()} ${await res.text()}`).toBeTruthy()
    return (await res.json().catch(() => null)) as T
  }

  async patch(path: string, data: object) {
    const res = await this.request.patch(`${API}${path}`, { headers: this.headers(), data })
    expect(res.ok(), `PATCH ${path}: ${res.status()}`).toBeTruthy()
  }

  async get<T>(path: string): Promise<T> {
    const res = await this.request.get(`${API}${path}`, { headers: this.headers() })
    expect(res.ok(), `GET ${path}: ${res.status()}`).toBeTruthy()
    return (await res.json()) as T
  }

  async upload(path: string, name: string, mimeType: string, buffer: Buffer) {
    const res = await this.request.post(`${API}${path}`, {
      headers: this.headers(),
      multipart: { file: { name, mimeType, buffer } },
    })
    expect(res.ok(), `upload ${path}: ${res.status()} ${await res.text()}`).toBeTruthy()
  }
}

async function registerAndLogin(request: APIRequestContext, user: typeof owner): Promise<string> {
  const reg = await request.post(`${API}/auth/register`, { data: user })
  expect(reg.status()).toBe(201)
  const res = await request.post(`${API}/auth/token`, { form: { username: user.email, password: user.password } })
  expect(res.ok()).toBeTruthy()
  return (await res.json()).access_token
}

function toRis(list: DemoArticle[]): string {
  return list
    .map((a) =>
      [
        'TY  - JOUR',
        `TI  - ${a.title}`,
        ...a.authors.map((au) => `AU  - ${au}`),
        `PY  - ${a.year}`,
        `JO  - ${a.journal}`,
        `AB  - ${a.abstract}`,
        ...(a.keywords ?? []).map((k) => `KW  - ${k}`),
        'ER  - ',
        '',
      ].join('\n')
    )
    .join('\n')
}

function aiDecision(stage: Stage, v: AiVerdict) {
  const types = Object.fromEntries(criteria.map((c) => [c.code, c.type]))
  return {
    stage,
    source: 'ai_agent',
    decision: v.decision,
    confidence_score: v.confidence,
    reasoning: v.summary,
    primary_exclusion_reason: v.exclusionReason,
    criteria_evaluations: Object.fromEntries(
      Object.entries(v.criteria).map(([code, [met, confidence, reasoning]]) => [
        code,
        {
          criterion_type: types[code],
          met,
          confidence,
          reasoning:
            reasoning ?? (met === null ? 'Not clearly reported.' : met ? 'Reported in the article.' : 'Does not apply.'),
        },
      ])
    ),
  }
}

/** Render the article's full text to a PDF with the browser, as a stand-in for the publisher's PDF. */
async function renderPdf(browser: Browser, a: DemoArticle): Promise<Buffer> {
  const page = await browser.newPage()
  const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;')
  await page.setContent(`
    <html><body style="font-family: Georgia, serif; font-size: 11pt; line-height: 1.5; margin: 2cm">
      <h1 style="font-size: 16pt">${esc(a.title)}</h1>
      <p>${esc(a.authors.join(', '))}. ${esc(a.journal)}, ${a.year}.</p>
      <p><b>Abstract.</b> ${esc(a.abstract)}</p>
      ${(a.fullText ?? []).map((p) => `<p>${esc(p)}</p>`).join('')}
    </body></html>`)
  const pdf = await page.pdf({ format: 'A4' })
  await page.close()
  return pdf
}

async function seed(request: APIRequestContext, browser: Browser) {
  const ownerApi = new Seeder(request, await registerAndLogin(request, owner))
  const reviewerApi = new Seeder(request, await registerAndLogin(request, reviewer))

  const { id: pid } = await ownerApi.post<{ id: number }>('/projects', project)
  await ownerApi.patch(`/projects/${pid}`, { required_reviewers: 2 })
  await ownerApi.post(`/projects/${pid}/members`, { email: reviewer.email, role: 'reviewer' })
  for (const c of criteria) await ownerApi.post(`/projects/${pid}/criteria`, c)

  await ownerApi.upload(
    `/projects/${pid}/upload/ris`,
    'medline-search-2024-03.ris',
    'application/x-research-info-systems',
    Buffer.from(toRis(articles))
  )
  await ownerApi.post(`/projects/${pid}/articles/start-screening`)

  const { data } = await ownerApi.get<{ data: { id: number; title: string }[] }>(
    `/projects/${pid}/articles?page=1&per_page=100`
  )
  const idOf = new Map(data.map((a) => [a.title, a.id]))
  expect(idOf.size).toBe(articles.length)

  const vote = (api: Seeder, aid: number, stage: Stage, decision: Vote, reasoning?: string, reason?: string) =>
    api.post(`/projects/${pid}/screening/articles/${aid}/decisions`, {
      stage,
      decision,
      source: 'human',
      reasoning,
      primary_exclusion_reason: decision === 'exclude' ? reason : undefined,
    })

  // Title / abstract: AI first, then both reviewers, then the owner settles disagreements
  for (const a of articles) {
    const aid = idOf.get(a.title)!
    await ownerApi.post(`/projects/${pid}/screening/articles/${aid}/decisions`, aiDecision('title_abstract', a.aiTa))
    await vote(ownerApi, aid, 'title_abstract', a.ta[0])
    await vote(reviewerApi, aid, 'title_abstract', a.ta[1])
    if (a.taResolution) {
      await ownerApi.post(`/projects/${pid}/screening/articles/${aid}/resolve`, {
        decision: a.taResolution,
        reason: 'Discussed at the consensus meeting.',
      })
    }
  }

  // Full text: upload the PDFs that could be retrieved, then AI and reviewer decisions
  for (const a of articles.filter((x) => x.fullText)) {
    const aid = idOf.get(a.title)!
    await ownerApi.upload(`/projects/${pid}/articles/${aid}/fulltext/upload`, 'full-text.pdf', 'application/pdf', await renderPdf(browser, a))
    if (a.aiFt) await ownerApi.post(`/projects/${pid}/screening/articles/${aid}/decisions`, aiDecision('full_text', a.aiFt))
    const [mine, theirs] = a.ft ?? [null, null]
    if (mine) await vote(ownerApi, aid, 'full_text', mine, a.ftNotes?.[0], a.ftReason)
    if (theirs) await vote(reviewerApi, aid, 'full_text', theirs, a.ftNotes?.[1], a.ftReason)
  }

  return { pid, token: ownerApi.token, heroId: idOf.get(heroTitle)! }
}

/** Save a PNG screenshot as WebP, encoded by the browser so no image tooling is needed. */
async function saveWebp(page: Page, png: Buffer, name: string) {
  const dataUrl = await page.evaluate(async (b64) => {
    const img = new Image()
    img.src = `data:image/png;base64,${b64}`
    await img.decode()
    const canvas = document.createElement('canvas')
    canvas.width = img.naturalWidth
    canvas.height = img.naturalHeight
    canvas.getContext('2d')!.drawImage(img, 0, 0)
    return canvas.toDataURL('image/webp', 0.86)
  }, png.toString('base64'))
  writeFileSync(`${OUT_DIR}${name}.webp`, Buffer.from(dataUrl.split(',')[1], 'base64'))
}

async function openAs(browser: Browser, token: string, theme: Theme): Promise<Page> {
  const context = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 2,
    colorScheme: theme,
    reducedMotion: 'reduce',
  })
  await context.addInitScript(
    ([t, th]) => {
      localStorage.setItem('excludr_token', t)
      localStorage.setItem('excludr-theme', th)
    },
    [token, theme]
  )
  // Every demo article already has an AI verdict; answer the lookahead as a configured server
  // would instead of showing the "no AI provider is configured" note
  await context.route('**/screening/run-ai', (route) => route.fulfill({ json: { article_ids: [] } }))
  return context.newPage()
}

async function settle(page: Page) {
  await page.waitForLoadState('networkidle')
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(300)
}

test('capture homepage screenshots', async ({ request, browser }) => {
  mkdirSync(OUT_DIR, { recursive: true })
  const { pid, token } = await seed(request, browser)

  for (const theme of THEMES) {
    const page = await openAs(browser, token, theme)

    // 1. Full-text screening: the article, the AI verdict and per-criterion reasoning
    await page.goto(`/projects/${pid}/screening?stage=full_text`)
    await expect(page.getByTestId('article-title')).toHaveText(heroTitle)
    await expect(page.getByTestId('ai-verdict')).toContainText('94%')
    for (const code of ['I1', 'I2']) {
      await page.getByTestId(`criterion-${code}`).getByRole('button', { name: 'Show AI reasoning' }).click()
    }
    await settle(page)
    await saveWebp(page, await page.screenshot(), `screening-${theme}`)

    // 2. Reviewer conflicts at full text
    await page.goto(`/projects/${pid}/conflicts`)
    await expect(page.getByTestId('conflict-card')).toHaveCount(2)
    await settle(page)
    await saveWebp(page, await page.screenshot(), `conflicts-${theme}`)

    // 3. PRISMA flow and agreement statistics
    await page.goto(`/projects/${pid}/reports`)
    await expect(page.getByTestId('prisma-diagram')).toBeVisible()
    await settle(page)
    // Grow the window to the whole report (a full-page capture would cut the sidebar short)
    const height = await page.evaluate(() => document.documentElement.scrollHeight)
    await page.setViewportSize({ width: VIEWPORT.width, height })
    await settle(page)
    await saveWebp(page, await page.screenshot(), `reports-${theme}`)

    await page.context().close()
  }
})
