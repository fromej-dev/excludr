# Excludr POC Plan

## Goal

A working prototype where a researcher can: create a project, define criteria, import articles, upload full-text PDFs, run AI screening against criteria, and review AI decisions in the UI.

---

## Current State

| Area | Status |
|------|--------|
| Auth & user management | Done |
| Project CRUD | Done |
| Article import (RIS/PubMed) | Done |
| Criteria management (CRUD, reorder) | Done |
| Screening endpoints (human decisions) | Done |
| Full-text PDF upload endpoint | Done |
| Frontend (auth, projects, criteria, basic screening) | Done |
| **AI screening agent** | **Not started** |
| **PDF text extraction** | **Not started** |
| **AI results in frontend** | **Not started** |
| **Batch screening orchestration** | **Not started** |

---

## What Needs to Be Built

### 1. PDF Text Extraction

**Problem:** The AI agent needs article text to evaluate. PDFs are uploaded but never parsed into text.

**Work:**
- Add a PDF text extraction utility (e.g., `pymupdf` or `pdfplumber`)
- Extract text when a PDF is uploaded and store it on the Article model
- Add a `full_text_content` field to Article (or store as a separate file and reference it)

**Files:**
- New: `app/features/research/pdf_extraction.py`
- Modify: `app/features/research/models.py` — add text content field
- Modify: `app/features/research/routers.py` — trigger extraction on PDF upload
- Migration for the new field

**Scope:** Small. Straightforward file parsing.

---

### 2. pydantic-ai Screening Agent

**Problem:** `app/features/research/agent.py` is empty. This is the core feature.

**Work:**
- Implement a pydantic-ai `Agent` with structured output (`ScreeningResult`)
- Dynamic system prompt that includes the project's review question and criteria
- Input: article title, abstract, full text (when available), and the project's criteria
- Output: per-criterion evaluations, overall decision (include/exclude/uncertain), confidence score, reasoning
- Save results as `ScreeningDecision` records with `source=ai_agent`

**Design:**
```
ScreeningResult (pydantic-ai structured output)
├── decision: include | exclude | uncertain
├── confidence: float (0.0–1.0)
├── criteria_evaluations: list
│   ├── criterion_code: str (e.g., "I1")
│   ├── met: bool | None
│   ├── confidence: float
│   └── reasoning: str
├── primary_exclusion_reason: str | None
└── summary_reasoning: str
```

**Agent context (dependencies):**
- Review question
- List of active criteria (code, type, description, rationale)
- Article text (title + abstract + full text if available)

**Files:**
- Implement: `app/features/research/agent.py`
- New: `app/features/research/schemas.py` — structured output models (if not already there)

**Scope:** Medium. Core logic, needs careful prompt engineering.

---

### 3. Screening API Endpoint for AI

**Problem:** No endpoint to trigger AI screening for an article or batch of articles.

**Work:**
- Add endpoint: `POST /projects/{id}/articles/{article_id}/screen-ai` — screen a single article with the AI agent
- Add endpoint: `POST /projects/{id}/screening/run-ai` — trigger AI screening for all articles in "screening" or "full_text_retrieved" status
- The single-article endpoint runs synchronously and returns the result
- The batch endpoint triggers a Prefect flow and returns a job ID

**Files:**
- Modify: `app/features/research/routers.py` or `app/features/screening/routers.py`
- New: `app/features/research/flows.py` — Prefect flow for batch AI screening
- Modify: `app/features/screening/services.py` — service method to run agent and save decision

**Scope:** Medium. Wiring agent to endpoints + Prefect flow.

---

### 4. Frontend: Display AI Screening Results

**Problem:** The screening UI exists but doesn't show AI decisions, reasoning, or per-criterion evaluations.

**Work:**
- Show AI decision badge on articles that have been AI-screened
- In the screening view, display AI reasoning and per-criterion evaluation alongside the human decision form
- Add a "Run AI Screening" button on the project view to trigger batch screening
- Show screening progress (how many screened, how many remaining)

**Components to build or update:**
- `ScreeningView.vue` — show AI decision if one exists for the current article
- New: `AiDecisionPanel.vue` — displays AI reasoning, per-criterion cards, confidence
- `ProjectOverview.vue` or `ArticlesView.vue` — add "Run AI Screening" action
- `screening.ts` store — add action to trigger AI screening endpoint

**Scope:** Medium. UI work, needs good design for readability.

---

### 5. End-to-End Flow Validation

**Problem:** The pieces need to work together as a coherent workflow.

**Work:**
- Verify the full flow: create project → add criteria → import articles → upload PDFs → extract text → run AI screening → review in UI
- Add integration tests covering the AI screening path (mocked LLM responses)
- Handle edge cases: articles without full text, criteria changes after screening, re-screening

**Files:**
- New: `tests/features/research/test_agent.py`
- New: `tests/features/screening/test_ai_screening.py`

**Scope:** Small-medium. Testing and fixing integration issues.

---

## Out of Scope for POC

These are valuable but not needed to demonstrate the core concept:

| Feature | Reason to defer |
|---------|----------------|
| Unpaywall auto-retrieval | Manual PDF upload is sufficient for demo |
| Title/abstract screening stage | Focus is full-text review |
| Conflict resolution (AI vs human) | Simple override is enough for POC |
| Export (CSV, RIS, PRISMA) | Not needed to show core screening works |
| User management / admin panel | Single-user demo is fine |
| Drag-and-drop criteria reorder in UI | API reorder works, UI polish can wait |
| Production Docker setup | Local dev is sufficient |
| Multi-model LLM support | Hardcoded Claude model is fine |

---

## Suggested Build Order

```
Step 1: PDF text extraction
   └── unblocks AI agent (needs text to evaluate)

Step 2: pydantic-ai screening agent
   └── core feature, can be tested via pytest independently

Step 3: AI screening API endpoints
   └── wires agent to the rest of the app

Step 4: Frontend AI display
   └── makes it visible and usable

Step 5: End-to-end testing
   └── validates the full flow works
```

Each step is independently testable and builds on the previous one.

---

## Definition of Done (POC)

A researcher can:
1. Log in and create a project with a review question
2. Define inclusion and exclusion criteria
3. Import articles from a RIS file
4. Upload a full-text PDF for an article
5. Trigger AI screening — the agent evaluates the article against all criteria
6. See the AI's decision, per-criterion reasoning, and confidence in the UI
7. Make their own human decision (agree or override)
8. See screening progress stats across the project
