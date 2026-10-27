import type { ProjectRole, ScreeningStats } from '@/types'

export type NextStepKind =
  | 'define-criteria'
  | 'import'
  | 'screen-title-abstract'
  | 'retrieve-fulltext'
  | 'screen-full-text'
  | 'resolve-conflicts'
  | 'complete'
  | 'waiting'
  | 'unavailable'

export type NextStepTarget =
  | { type: 'route'; name: string; query?: Record<string, string> }
  | { type: 'anchor'; id: string }

export interface NextStepInput {
  /** All loads (role, nav counts, stats) have finished, successfully or not; false means keep waiting. */
  settled: boolean
  role: ProjectRole | null
  /** Active criteria; null while unknown. */
  criteriaCount: number | null
  totalArticles: number
  stats: ScreeningStats | null
  /** Articles waiting for the signed-in user at each stage; null while unknown / not a reviewer. */
  pendingTitleAbstract: number | null
  pendingFullText: number | null
  /** Unresolved conflicts (owner only); null while unknown. */
  conflicts: number | null
}

export interface NextStep {
  kind: NextStepKind
  title: string
  description: string
  /** Absent for read-only variants without a useful destination. */
  action?: { label: string; target: NextStepTarget }
}

const UNAVAILABLE: NextStep = {
  kind: 'unavailable',
  title: "Couldn't load the next step",
  description: 'Some project data failed to load, so we cannot tell what comes next.',
}

const plural = (n: number, one: string, many: string): string => `${n} ${n === 1 ? one : many}`

/**
 * Pick the single most relevant next action. Returns null only while loads are still in flight; once
 * settled it decides with what it has (unknown counts never block) and falls back to an 'unavailable' step.
 */
export function computeNextStep(i: NextStepInput): NextStep | null {
  if (!i.settled) return null
  if (i.role === null) return UNAVAILABLE
  const owner = i.role === 'owner'
  const reviewer = owner || i.role === 'reviewer'
  const hasArticles = i.totalArticles > 0

  // Setup comes first
  if (i.criteriaCount === 0) {
    return owner
      ? {
          kind: 'define-criteria',
          title: 'Define your inclusion/exclusion criteria',
          description: 'Screening decisions are made against these criteria, so set them before anything else.',
          action: { label: 'Add criteria', target: { type: 'route', name: 'project-criteria' } },
        }
      : {
          kind: 'waiting',
          title: 'Waiting for criteria',
          description: 'The project owner has not defined inclusion/exclusion criteria yet.',
        }
  }
  if (!hasArticles) {
    return owner
      ? {
          kind: 'import',
          title: 'Import articles',
          description: 'Upload a RIS file or a PubMed export to start the review.',
          action: { label: 'Import articles', target: { type: 'anchor', id: 'import' } },
        }
      : {
          kind: 'waiting',
          title: 'Waiting for articles',
          description: 'The project owner has not imported any articles yet.',
        }
  }

  const ta = i.pendingTitleAbstract ?? 0
  const ft = i.pendingFullText ?? 0
  const awaiting = i.stats?.awaiting_full_text ?? 0
  const conflicts = i.conflicts ?? 0

  if (reviewer && ta > 0) {
    return {
      kind: 'screen-title-abstract',
      title: `Screen ${plural(ta, 'article', 'articles')}`,
      description: 'Title and abstract screening is waiting for your decisions.',
      action: {
        label: 'Start screening',
        target: { type: 'route', name: 'project-screening', query: { stage: 'title_abstract' } },
      },
    }
  }
  if (owner && awaiting > 0) {
    return {
      kind: 'retrieve-fulltext',
      title: 'Retrieve full texts',
      description: `${plural(awaiting, 'article is', 'articles are')} waiting for a full text before full-text screening.`,
      action: { label: 'Retrieve full texts', target: { type: 'anchor', id: 'fulltext' } },
    }
  }
  if (reviewer && ft > 0) {
    return {
      kind: 'screen-full-text',
      title: `Screen ${plural(ft, 'full text', 'full texts')}`,
      description: 'Full-text screening is waiting for your decisions.',
      action: {
        label: 'Start full-text screening',
        target: { type: 'route', name: 'project-screening', query: { stage: 'full_text' } },
      },
    }
  }
  if (owner && conflicts > 0) {
    return {
      kind: 'resolve-conflicts',
      title: `Resolve ${plural(conflicts, 'conflict', 'conflicts')}`,
      description: 'Reviewers disagree on these articles. As owner you make the final call.',
      action: { label: 'Resolve conflicts', target: { type: 'route', name: 'project-conflicts' } },
    }
  }

  // Nothing fired. If a count we rely on is unknown we cannot claim the review is done.
  const unknown =
    i.stats === null ||
    (reviewer && (i.pendingTitleAbstract === null || i.pendingFullText === null)) ||
    (owner && i.conflicts === null)
  if (unknown && (reviewer || i.stats === null)) return UNAVAILABLE

  const stillOpen = (i.stats?.awaiting_screening ?? 0) > 0 || awaiting > 0
  if (!reviewer && stillOpen) {
    return {
      kind: 'waiting',
      title: 'Review in progress',
      description: 'You have read-only access. Follow progress below or browse the articles.',
      action: { label: 'Browse articles', target: { type: 'route', name: 'project-articles' } },
    }
  }
  return {
    kind: 'complete',
    title: stillOpen ? 'Nothing left for you to do right now' : 'Review complete',
    description: stillOpen
      ? 'Other reviewers still have articles to screen. See the PRISMA report for the current picture.'
      : 'Every article has a decision. See the PRISMA report.',
    action: { label: 'Open PRISMA report', target: { type: 'route', name: 'project-reports' } },
  }
}
