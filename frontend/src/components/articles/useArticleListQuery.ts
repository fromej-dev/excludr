import { computed } from 'vue'
import { useRoute, useRouter, type LocationQuery, type LocationQueryRaw } from 'vue-router'
import type { ArticleListOptions, ArticleSortField, ArticleStatus, FinalDecision, SortOrder } from '@/types'

export type FullTextFilter = '' | 'has' | 'missing'

export const PAGE_SIZES = [25, 50, 100] as const
export const DEFAULT_PER_PAGE = 25

const STATUSES: ArticleStatus[] = [
  'imported',
  'screening',
  'awaiting_full_text',
  'full_text_retrieved',
  'included',
  'excluded',
]
const DECISIONS: FinalDecision[] = ['pending', 'included', 'excluded']
const SORT_FIELDS: ArticleSortField[] = ['title', 'year', 'status']

export interface ArticleListState {
  q: string
  status: ArticleStatus | ''
  decision: FinalDecision | ''
  fullText: FullTextFilter
  sort: ArticleSortField | ''
  order: SortOrder
  page: number
  perPage: number
}

const first = (v: LocationQuery[string]): string => (Array.isArray(v) ? (v[0] ?? '') : (v ?? ''))

export const parseArticleQuery = (query: LocationQuery): ArticleListState => {
  const status = first(query.status) as ArticleStatus
  const decision = first(query.decision) as FinalDecision
  const fullText = first(query.full_text)
  const sort = first(query.sort) as ArticleSortField
  const perPage = Number(first(query.per_page))
  const page = Number(first(query.page))
  return {
    q: first(query.q),
    status: STATUSES.includes(status) ? status : '',
    decision: DECISIONS.includes(decision) ? decision : '',
    fullText: fullText === 'has' || fullText === 'missing' ? fullText : '',
    sort: SORT_FIELDS.includes(sort) ? sort : '',
    order: first(query.order) === 'desc' ? 'desc' : 'asc',
    page: Number.isInteger(page) && page > 0 ? page : 1,
    perPage: (PAGE_SIZES as readonly number[]).includes(perPage) ? perPage : DEFAULT_PER_PAGE,
  }
}

/** Only non-default values are written, so the URL stays short. */
export const serializeArticleState = (s: ArticleListState): LocationQueryRaw => {
  const out: Record<string, string> = {}
  if (s.q.trim()) out.q = s.q.trim()
  if (s.status) out.status = s.status
  if (s.decision) out.decision = s.decision
  if (s.fullText) out.full_text = s.fullText
  if (s.sort) {
    out.sort = s.sort
    out.order = s.order
  }
  if (s.page > 1) out.page = String(s.page)
  if (s.perPage !== DEFAULT_PER_PAGE) out.per_page = String(s.perPage)
  return out
}

export const toListOptions = (s: ArticleListState): ArticleListOptions => ({
  status: s.status || undefined,
  final_decision: s.decision || undefined,
  has_full_text: s.fullText === 'has' ? true : s.fullText === 'missing' ? false : undefined,
  search: s.q.trim() || undefined,
  sort_by: s.sort || undefined,
  order: s.sort ? s.order : undefined,
  page: s.page,
  per_page: s.perPage,
})

/** Articles list state (search, filters, sort, paging) kept in the URL query. */
export function useArticleListQuery() {
  const route = useRoute()
  const router = useRouter()

  const state = computed(() => parseArticleQuery(route.query))

  const hasFilters = computed(() => {
    const s = state.value
    return !!(s.q.trim() || s.status || s.decision || s.fullText)
  })

  /** Merge a patch into the state. Anything other than a page change resets to page 1. */
  const update = (patch: Partial<ArticleListState>) => {
    const next: ArticleListState = { ...state.value, ...patch }
    if (!('page' in patch)) next.page = 1
    return router.replace({ query: serializeArticleState(next) })
  }

  const clearFilters = () => update({ q: '', status: '', decision: '', fullText: '' })

  /** Click on a sortable header: asc -> desc -> off. */
  const toggleSort = (field: ArticleSortField) => {
    const s = state.value
    if (s.sort !== field) return update({ sort: field, order: 'asc' })
    if (s.order === 'asc') return update({ order: 'desc' })
    return update({ sort: '', order: 'asc' })
  }

  return { state, hasFilters, update, clearFilters, toggleSort }
}
