// Auth types
export interface LoginCredentials {
  username: string // email
  password: string
}

export interface RegisterData {
  email: string
  name: string
  password: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

// User types
export interface User {
  id: number
  email: string
  name: string
  is_active: boolean
  is_superuser: boolean
  is_verified: boolean
  created_at: string
  updated_at: string
}

// Project types
export interface Project {
  id: number
  name: string
  description?: string
  review_question?: string
  created_at: string
  updated_at: string
  owner_id: number
  number_of_articles: number
  required_reviewers: number
}

export interface ProjectCreate {
  name: string
  description?: string
  review_question?: string
}

export interface ProjectUpdate {
  name?: string
  description?: string
  review_question?: string
  required_reviewers?: 1 | 2
}

// Criteria types
export type CriterionType = 'inclusion' | 'exclusion'

export interface Criterion {
  id: number
  project_id: number
  type: CriterionType
  code: string
  description: string
  rationale?: string
  order: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface CriterionCreate {
  type: CriterionType
  code: string
  description: string
  rationale?: string
  order?: number
}

export interface CriterionUpdate {
  type?: CriterionType
  code?: string
  description?: string
  rationale?: string
  order?: number
  is_active?: boolean
}

export interface CriteriaReorder {
  criterion_ids: number[]
}

// Article types
export type ArticleStatus =
  | 'imported'
  | 'screening'
  | 'awaiting_full_text'
  | 'full_text_retrieved'
  | 'included'
  | 'excluded'

export type FinalDecision = 'pending' | 'included' | 'excluded'

export type ScreeningStage = 'title_abstract' | 'full_text' | 'completed'

export interface Article {
  id: number
  project_id: number
  title?: string
  authors: string[]
  abstract?: string
  publication_date?: string
  year?: number
  journal?: string
  doi?: string
  pmid?: string
  keywords: string[]
  full_text_retrieved?: boolean
  full_text_path?: string | null
  full_text_content?: string | null
  status: ArticleStatus
  current_stage: ScreeningStage
  final_decision: FinalDecision
  created_at: string
  updated_at: string
}

export interface ArticleStats {
  total: number
  by_status: Record<ArticleStatus, number>
  by_decision: Record<FinalDecision, number>
}

// Screening types
export type ScreeningDecisionType = 'include' | 'exclude' | 'uncertain'

export type DecisionSource = 'ai_agent' | 'human'

export interface CriteriaEvaluation {
  criterion_type: string
  met: boolean | null
  confidence: number
  reasoning: string
}

export interface CriterionEvaluation {
  criterion_code: string
  criterion_type: string
  met: boolean | null
  confidence: number
  reasoning: string
}

export interface ScreeningDecision {
  id: number
  article_id: number
  stage: ScreeningStage
  decision: ScreeningDecisionType
  source: DecisionSource
  confidence_score?: number
  reasoning?: string
  primary_exclusion_reason?: string
  criteria_evaluations?: CriterionEvaluation[] | Record<string, CriteriaEvaluation>
  reviewer_id?: number | null
  is_resolution?: boolean
  model_name?: string | null
  criteria_snapshot?: Record<string, number> | null
  created_at: string
}

export interface ScreeningDecisionCreate {
  stage: ScreeningStage
  decision: ScreeningDecisionType
  source: DecisionSource
  confidence_score?: number
  reasoning?: string
  primary_exclusion_reason?: string
  criteria_evaluations?: Record<string, CriteriaEvaluation>
}

export interface ScreeningStats {
  total_articles: number
  screened_title_abstract: number
  screened_full_text: number
  included: number
  excluded: number
  uncertain: number
  awaiting_screening: number
  awaiting_full_text: number
}

// Pagination types (fastapi-fsp structure)
export interface PaginationMeta {
  total_items: number
  per_page: number
  current_page: number
  total_pages: number
}

export interface PaginationLinks {
  self: string
  first: string
  next: string | null
  prev: string | null
  last: string
}

export interface PaginatedResponse<T> {
  data: T[]
  meta: {
    pagination: PaginationMeta
    filters?: any[]
    sort?: any
  }
  links: PaginationLinks
}

// Roles and members
export type ProjectRole = 'owner' | 'reviewer' | 'viewer'

export interface ProjectMember {
  user_id: number
  email: string
  name: string
  role: ProjectRole
  created_at: string
}

// Imports
export interface ImportBatch {
  id: number
  project_id: number
  filename: string
  format: string
  records_found: number
  imported: number
  duplicates: number
  created_at: string
  created_by: number | null
}

export type ImportKind = 'ris' | 'pubmed'

export interface ImportResult {
  status: string
  message?: string
  articles_created?: number
  articles_updated?: number
  duplicates?: number
  duplicates_by_title_year?: number
  abstracts_fetched?: number
}

export interface UploadResponse {
  message: string
  result: ImportResult
}

export interface FullTextUploadResponse {
  message: string
  text_extracted: boolean
  text_length: number
}

// Screening: next article, AI batch, conflicts
export interface NextArticleResponse {
  message?: string
  article: Article | null
}

export interface StaleAiResponse {
  article_ids: number[]
  count: number
}

export interface RunAiResponse {
  message: string
  article_count: number
}

export interface AiBatchProgress {
  screened: number
  errors: number
  total: number
}

export interface ReviewerDecision {
  decision_id: number
  reviewer_id: number | null
  reviewer_name: string | null
  decision: ScreeningDecisionType
  reasoning: string | null
  primary_exclusion_reason: string | null
  confidence_score: number | null
  created_at: string | null
}

export interface Conflict {
  article_id: number
  title: string | null
  stage: ScreeningStage
  decisions: ReviewerDecision[]
}

export interface ResolveRequest {
  decision: Exclude<ScreeningDecisionType, 'uncertain'>
  reason: string
  primary_exclusion_reason?: string
}

export interface AiDecisionSummary {
  decision_id: number
  decision: ScreeningDecisionType
  confidence_score: number | null
  reasoning: string | null
}

export interface AiDisagreement {
  article_id: number
  title: string | null
  stage: ScreeningStage
  ai: AiDecisionSummary
  human_decision: ScreeningDecisionType
  human_is_resolution: boolean
}

export interface HumanAgreement {
  reviewers: number[]
  n_articles: number
  percent_agreement: number | null
  cohens_kappa: number | null
}

export interface AiAgreement {
  n_articles: number
  true_positives: number
  false_positives: number
  true_negatives: number
  false_negatives: number
  accuracy: number | null
  sensitivity: number | null
  specificity: number | null
  cohens_kappa: number | null
  ai_uncertain: number
  without_ai_decision: number
}

export interface Agreement {
  stage: ScreeningStage
  required_reviewers: number
  human_vs_human: HumanAgreement | null
  ai_vs_human: AiAgreement
}

// Reporting
export interface PrismaSource {
  filename: string
  format: string
  records_found: number
  imported: number
  duplicates: number
  imported_at: string | null
}

export interface PrismaFlow {
  identification: {
    sources: PrismaSource[]
    records_identified: number
    duplicates_removed: number
    records_after_duplicates_removed: number
  }
  screening: { records_screened: number; records_excluded: number }
  retrieval: { reports_sought: number; reports_not_retrieved: number }
  eligibility: {
    reports_assessed: number
    reports_excluded: number
    exclusion_reasons: Array<{ reason: string; count: number }>
  }
  included: { studies_included: number }
}

export type ExportFormat = 'csv' | 'ris'

// Audit
export interface AuditEvent {
  id: number
  project_id: number
  user_id: number | null
  action: string
  entity_type: string
  entity_id: number | null
  details: Record<string, unknown> | null
  created_at: string
}

// WebSocket types
export type MessageType =
  | 'text'
  | 'join_room'
  | 'leave_room'
  | 'room_message'
  | 'broadcast'
  | 'error'
  | 'info'
  | 'notification'

export type NotificationLevel = 'info' | 'success' | 'warning' | 'error'

export interface WebSocketMessage {
  type: MessageType
  data: any
  room?: string
}

export interface WebSocketResponse {
  type: MessageType
  message: string
  data?: {
    level?: NotificationLevel
    notification?: boolean
    project_id?: number
    user_id?: number
    rooms?: string[]
    [key: string]: any
  }
  room?: string
}

export interface ToastNotification {
  id: string
  message: string
  level: NotificationLevel
  duration?: number
  timestamp: number
}
