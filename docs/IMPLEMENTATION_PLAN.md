# Excludr: Agentic Systematic Review Platform

## Current State Summary

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: Foundation & Prefect | **COMPLETE** | Models, migrations, Prefect flows all done |
| Phase 2: Criteria Management | **COMPLETE** | Full CRUD, reorder, services implemented |
| Phase 3: AI Screening Agent | **PARTIAL** | Endpoints exist, pydantic-ai agent not implemented |
| Phase 4: Full-Text Retrieval | **NOT STARTED** | No Unpaywall integration |
| Phase 5: Frontend | **IN PROGRESS** | Vue 3 + shadcn-vue implementation |
| Phase 6: Screening Interface | **NOT STARTED** | Depends on Phase 5 |

**Implemented:**
- FastAPI backend with feature-based structure
- User auth (JWT, registration, roles)
- Project CRUD with ownership
- RIS file upload → Prefect parses to Article model
- Article model with status/stage fields and AI-ready fields
- Criteria management (CRUD, reorder, services)
- Screening models and endpoints (ScreeningDecision)
- Article CRUD and stats endpoints
- Docker Compose: PostgreSQL, Redis
- Prefect server and worker

**Scaffolded but incomplete:**
- `app/features/research/agent.py` - pydantic-ai agent not implemented
- Full-text retrieval (Unpaywall integration pending)

**In Progress:**
- Frontend (Vue 3 + Pinia + shadcn-vue)

---

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Frontend   │────▶│   FastAPI   │────▶│  PostgreSQL │
│   (Vue 3)   │     │   Backend   │     │             │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                    ┌──────▼──────┐
                    │   Prefect   │
                    │   Server    │
                    └──────┬──────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   RIS Parser       Full-Text           AI Screening
     Flow          Retrieval           Agent Flow
                     Flow            (pydantic-ai)
                                          │
                                    ┌─────▼─────┐
                                    │  Claude   │
                                    │   API     │
                                    └───────────┘
```

---

## New Data Models

### 1. Criterion (inclusion/exclusion criteria)
```
Criterion
├── project_id (FK)
├── type: inclusion | exclusion
├── code: "I1", "E1", etc.
├── description
├── rationale (optional)
├── order, is_active
```

### 2. ScreeningDecision (AI + human decisions)
```
ScreeningDecision
├── article_id (FK)
├── stage: title_abstract | full_text
├── decision: include | exclude | uncertain
├── source: ai_agent | human
├── criteria_evaluations (JSON)
├── reasoning, confidence_score
├── reviewer_id (FK, optional)
```

### 3. Article model updates
- Add `status` enum: imported → screening → awaiting_full_text → full_text_retrieved → included/excluded
- Add `current_stage`, `final_decision`

---

## Implementation Phases

### Phase 1: Foundation & Prefect Migration
- Create new models (Criterion, ScreeningDecision)
- Update Article model with status/stage fields
- Run Alembic migration
- Set up Prefect, migrate RIS parser from Celery
- Add article CRUD endpoints
- Remove Celery

**Files to modify:**
- `app/features/research/models.py` - add ArticleStatus, update Article
- `app/features/projects/tasks.py` → `app/features/projects/flows.py`
- `app/core/celery.py` → `app/core/prefect_config.py`
- New: `app/features/criteria/` module
- New: `app/features/screening/` module

### Phase 2: Criteria Management
- Create criteria feature (models, routers, services)
- Add `review_question` field to Project
- Endpoints: CRUD for criteria, reorder

### Phase 3: AI Screening Agent
- Implement pydantic-ai abstract screening agent in `app/features/research/agent.py`
- Structured output: decision + per-criterion evaluations + reasoning
- Prefect flow for batch screening
- Screening decision endpoints

### Phase 4: Full-Text Retrieval
- Unpaywall API integration (lookup DOI → get open access PDF)
- PDF download and storage
- Prefect flow for batch retrieval
- Manual upload endpoint

### Phase 5: Frontend (Vue 3 + Pinia + shadcn-vue)

#### Step 1: Project Setup
```bash
npm create vite@latest frontend -- --template vue-ts
cd frontend
npm install vue-router@4 pinia @vueuse/core axios
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
npx shadcn-vue@latest init
```

Install shadcn-vue components:
- button, card, dialog, dropdown-menu, form, input, label
- pagination, progress, select, skeleton, table, tabs, textarea
- toast, tooltip, badge, alert, alert-dialog, checkbox, sheet

#### Step 2: Core Infrastructure
| File | Purpose |
|------|---------|
| `src/types/*.ts` | TypeScript interfaces for API responses |
| `src/composables/useApi.ts` | Axios wrapper with JWT auth |
| `src/router/index.ts` | Vue Router with auth guards |
| `src/main.ts` | App entry with Pinia setup |

#### Step 3: Pinia Stores
| Store | Responsibilities |
|-------|------------------|
| `auth.ts` | JWT token, user state, login/register/logout |
| `projects.ts` | Project CRUD, RIS upload |
| `articles.ts` | Article list, filters, stats, pagination |
| `criteria.ts` | Criteria CRUD, reorder |
| `screening.ts` | Screening queue, decisions, stats |

#### Step 4: Views Implementation Order

**4.1 Auth Views**
- `LoginView.vue` - Email/password form, JWT token storage
- `RegisterView.vue` - Registration form, auto-login

**4.2 Dashboard & Project Management**
- `DashboardView.vue` - Project grid with cards
- `ProjectView.vue` - Parent layout with tabs
- Components: `ProjectCard`, `ProjectForm`, `ProjectDeleteDialog`

**4.3 Criteria Management**
- `CriteriaView.vue` - Split view: inclusion/exclusion lists
- Components: `CriterionCard`, `CriterionForm`, `CriteriaDragList`
- Drag-and-drop via `@vueuse/integrations/useSortable`

**4.4 Articles**
- `ArticlesView.vue` - Filterable table with stats
- `ArticleDetailView.vue` - Full article with decisions tab
- Components: `ArticleList`, `ArticleFilters`, `ArticleStats`

**4.5 File Upload**
- `RisUploader.vue` - RIS import with progress indicator
- `FullTextUploader.vue` - PDF upload for individual articles

**4.6 Screening Interface** (Phase 6 overlap)
- `ScreeningView.vue` - Main screening workflow
- Components: `ScreeningCard`, `ScreeningDecisionPanel`, `ScreeningCriteriaChecklist`
- `useScreening.ts` composable for workflow logic
- Keyboard shortcuts (i=include, e=exclude, u=uncertain)

#### Step 5: Project Structure
```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/           # shadcn-vue (auto-generated)
│   │   ├── layout/       # AppHeader, AppSidebar, AppLayout
│   │   ├── articles/     # ArticleCard, ArticleList, ArticleFilters
│   │   ├── criteria/     # CriterionCard, CriteriaList, CriteriaDragList
│   │   ├── projects/     # ProjectCard, ProjectForm
│   │   ├── screening/    # ScreeningCard, DecisionPanel
│   │   └── upload/       # RisUploader, FullTextUploader
│   ├── composables/      # useApi, useAuth, useScreening
│   ├── stores/           # Pinia stores
│   ├── types/            # TypeScript interfaces
│   ├── views/            # Page components
│   └── router/           # Route definitions
```

### Phase 6: Screening Interface

#### Main Components
- `ScreeningView.vue` - Main screening workflow view
- `ScreeningCard.vue` - Article display with abstract
- `ScreeningDecisionPanel.vue` - Decision buttons and criteria checklist
- `ScreeningCriteriaChecklist.vue` - Per-criterion evaluation

#### Features
- Screening queue (one article at a time)
- AI decision display with reasoning
- Include/Exclude/Uncertain buttons with optional criterion selection
- Keyboard shortcuts:
  - `i` = Include
  - `e` = Exclude
  - `u` = Uncertain
  - `n` = Next article
  - `p` = Previous article
- Conflict resolution for AI vs human disagreements
- Progress indicator and stats

#### API Integration
- `GET /projects/{id}/screening/next` - Get next article to screen
- `POST /projects/{id}/articles/{id}/decisions` - Save decision
- `GET /projects/{id}/screening/stats` - Screening progress stats

### Phase 7: Polish & Export
- Export to CSV/RIS
- PRISMA flow diagram
- Statistics dashboard

---

## Key API Endpoints to Add

```
# Criteria
POST/GET/PATCH/DELETE /projects/{id}/criteria

# Articles
GET    /projects/{id}/articles
GET    /projects/{id}/articles/{id}
GET    /projects/{id}/articles/stats

# Screening
GET    /projects/{id}/screening/next?stage=title_abstract
POST   /projects/{id}/articles/{id}/decisions
POST   /projects/{id}/screening/start
GET    /projects/{id}/screening/status

# Full-text
POST   /projects/{id}/fulltext/retrieve
POST   /projects/{id}/articles/{id}/fulltext/upload
```

---

## AI Agent Design (pydantic-ai)

```python
# Structured output
class AbstractScreeningResult(BaseModel):
    decision: Literal["include", "exclude", "uncertain"]
    overall_confidence: float
    inclusion_criteria_evaluations: List[CriterionEvaluation]
    exclusion_criteria_evaluations: List[CriterionEvaluation]
    primary_exclusion_reason: Optional[str]
    summary_reasoning: str

# Agent with dynamic system prompt based on project criteria
abstract_screening_agent = Agent(
    'anthropic:claude-sonnet-4-20250514',
    result_type=AbstractScreeningResult,
    system_prompt="You are an expert systematic review screener..."
)
```

---

## Configuration Additions

```python
# app/core/config.py
prefect_api_url: str = "http://localhost:4200/api"
anthropic_api_key: str
default_llm_model: str = "claude-sonnet-4-20250514"
screening_confidence_threshold: float = 0.7
unpaywall_email: str
pdf_storage_path: str = "/data/pdfs"
```

---

## Docker Services Update

Remove Flower, add Prefect:
```yaml
prefect-server:
  image: prefecthq/prefect:2-python3.12
  ports: ["4200:4200"]

prefect-worker:
  build: ./docker/prefect_worker
```

---

## Frontend Structure (Vue 3)

```
frontend/
├── src/
│   ├── views/
│   │   ├── LoginView.vue
│   │   ├── DashboardView.vue
│   │   ├── ProjectView.vue
│   │   ├── CriteriaView.vue
│   │   ├── ArticlesView.vue
│   │   └── ScreeningView.vue
│   ├── stores/
│   │   ├── auth.ts          # JWT token, user state
│   │   ├── projects.ts      # Project list and current project
│   │   ├── articles.ts      # Article list, filters, pagination
│   │   └── screening.ts     # Screening queue state
│   ├── composables/
│   │   ├── useApi.ts        # Axios wrapper with auth
│   │   └── useScreening.ts  # Screening workflow logic
│   └── components/
│       ├── criteria/        # CriteriaList, CriterionForm
│       ├── articles/        # ArticleTable, ArticleDetail
│       └── screening/       # ScreeningCard, DecisionButtons
```

---

## Verification

1. **After Phase 1**: `pytest` passes, Prefect UI shows RIS import flow
2. **After Phase 3**: AI can screen test articles via API
3. **After Phase 5**: Can log in, create project, add criteria, import RIS via Vue UI
4. **After Phase 6**: Can screen articles with AI assistance in UI