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
  token_type: string
}

// User types
export interface User {
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
  met: boolean
  reasoning?: string
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
  criteria_evaluations?: Record<string, CriteriaEvaluation>
  reviewer_id?: number
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
