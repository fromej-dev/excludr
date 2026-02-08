import { test as base, expect, type Page, type APIRequestContext } from '@playwright/test'

const API_BASE = '/api/v1'

/** Unique suffix to isolate parallel test data. */
function uid(): string {
  return Math.random().toString(36).slice(2, 10)
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TestUser {
  email: string
  name: string
  password: string
  token: string
}

export interface TestProject {
  id: number
  name: string
  description: string
  review_question: string
}

export interface TestArticle {
  id: number
  title: string
  project_id: number
}

export interface TestCriterion {
  id: number
  code: string
  type: 'inclusion' | 'exclusion'
  description: string
  project_id: number
}

// ---------------------------------------------------------------------------
// API helpers — seed data via backend API (much faster than UI clicks)
// ---------------------------------------------------------------------------

export class ApiHelper {
  constructor(private request: APIRequestContext) {}

  async register(overrides?: Partial<{ email: string; name: string; password: string }>): Promise<TestUser> {
    const id = uid()
    const email = overrides?.email ?? `e2e_${id}@test.com`
    const name = overrides?.name ?? `E2E User ${id}`
    const password = overrides?.password ?? 'TestPass123!'

    const res = await this.request.post(`${API_BASE}/auth/register`, {
      data: { email, name, password },
    })
    expect(res.status()).toBe(201)

    // Login to get token
    const loginRes = await this.request.post(`${API_BASE}/auth/token`, {
      form: { username: email, password },
    })
    expect(loginRes.status()).toBe(200)
    const { access_token } = await loginRes.json()

    return { email, name, password, token: access_token }
  }

  async login(email: string, password: string): Promise<string> {
    const res = await this.request.post(`${API_BASE}/auth/token`, {
      form: { username: email, password },
    })
    expect(res.status()).toBe(200)
    const data = await res.json()
    return data.access_token
  }

  async createProject(token: string, overrides?: Partial<{ name: string; description: string; review_question: string }>): Promise<TestProject> {
    const id = uid()
    const res = await this.request.post(`${API_BASE}/projects`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        name: overrides?.name ?? `Project ${id}`,
        description: overrides?.description ?? `E2E test project ${id}`,
        review_question: overrides?.review_question ?? 'What is the effect of X on Y?',
      },
    })
    expect(res.status()).toBe(201)
    return await res.json()
  }

  async createCriterion(
    token: string,
    projectId: number,
    data: { type: 'inclusion' | 'exclusion'; code: string; description: string; rationale?: string },
  ): Promise<TestCriterion> {
    const res = await this.request.post(`${API_BASE}/projects/${projectId}/criteria`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        type: data.type,
        code: data.code,
        description: data.description,
        rationale: data.rationale ?? 'E2E test rationale',
      },
    })
    expect(res.status()).toBe(201)
    return await res.json()
  }

  async uploadRisFile(token: string, projectId: number, risContent: string): Promise<void> {
    const res = await this.request.post(`${API_BASE}/projects/${projectId}/upload/ris`, {
      headers: { Authorization: `Bearer ${token}` },
      multipart: {
        file: {
          name: 'test_articles.ris',
          mimeType: 'application/x-research-info-systems',
          buffer: Buffer.from(risContent),
        },
      },
    })
    expect(res.ok()).toBeTruthy()
  }

  async startScreening(token: string, projectId: number): Promise<{ count: number }> {
    const res = await this.request.post(`${API_BASE}/projects/${projectId}/articles/start-screening`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(res.ok()).toBeTruthy()
    return await res.json()
  }

  async getArticles(token: string, projectId: number): Promise<{ data: TestArticle[] }> {
    const res = await this.request.get(`${API_BASE}/projects/${projectId}/articles`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(res.ok()).toBeTruthy()
    return await res.json()
  }
}

// ---------------------------------------------------------------------------
// Page helpers — common UI interactions
// ---------------------------------------------------------------------------

export class PageHelper {
  constructor(private page: Page) {}

  /** Login via the UI login form. */
  async loginViaUI(email: string, password: string) {
    await this.page.goto('/login')
    await this.page.locator('#email').fill(email)
    await this.page.locator('#password').fill(password)
    await this.page.locator('button[type="submit"]').click()
    // Wait for redirect to dashboard
    await this.page.waitForURL('/', { timeout: 10_000 })
  }

  /** Set token directly in localStorage and navigate (faster than UI login). */
  async loginDirect(token: string) {
    await this.page.goto('/login')
    await this.page.evaluate((t) => {
      localStorage.setItem('excludr_token', t)
    }, token)
    await this.page.goto('/')
    await this.page.waitForURL('/')
  }

  /** Navigate to a project's tab. */
  async goToProjectTab(projectId: number, tab: 'overview' | 'criteria' | 'articles' | 'screening') {
    const paths: Record<string, string> = {
      overview: `/projects/${projectId}`,
      criteria: `/projects/${projectId}/criteria`,
      articles: `/projects/${projectId}/articles`,
      screening: `/projects/${projectId}/screening`,
    }
    await this.page.goto(paths[tab])
    await this.page.waitForLoadState('networkidle')
  }
}

// ---------------------------------------------------------------------------
// Generate minimal valid RIS content for importing articles
// ---------------------------------------------------------------------------

export function generateRisContent(count: number = 3): string {
  const articles: string[] = []
  for (let i = 1; i <= count; i++) {
    const id = uid()
    articles.push(
      [
        'TY  - JOUR',
        `TI  - E2E Test Article ${id} Number ${i}`,
        `AU  - Author, Test${i}`,
        `AU  - Writer, E2E${i}`,
        `AB  - This is the abstract for test article number ${i}. It discusses the effects of intervention X on outcome Y in population Z.`,
        `PY  - ${2020 + i}`,
        `JO  - Journal of E2E Testing`,
        `VL  - ${i}`,
        `IS  - 1`,
        `SP  - ${i * 10}`,
        `EP  - ${i * 10 + 9}`,
        `DO  - 10.1234/e2e-${id}`,
        `KW  - e2e testing`,
        `KW  - systematic review`,
        'ER  - ',
        '',
      ].join('\n'),
    )
  }
  return articles.join('\n')
}

// ---------------------------------------------------------------------------
// Extended test fixture
// ---------------------------------------------------------------------------

type Fixtures = {
  api: ApiHelper
  pageHelper: PageHelper
  testUser: TestUser
}

export const test = base.extend<Fixtures>({
  api: async ({ request }, use) => {
    await use(new ApiHelper(request))
  },

  pageHelper: async ({ page }, use) => {
    await use(new PageHelper(page))
  },

  /** A pre-registered, logged-in test user. */
  testUser: async ({ api }, use) => {
    const user = await api.register()
    await use(user)
  },
})

export { expect }
