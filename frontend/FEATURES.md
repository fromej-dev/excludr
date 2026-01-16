# Excludr Frontend Features

## Overview
A complete Vue 3 frontend for systematic review management, built with TypeScript, Tailwind CSS, and modern Vue ecosystem tools.

## Authentication

### Login
- Email/password authentication
- JWT token management
- Error handling with user feedback
- Auto-redirect after successful login
- Link to registration page

**Location:** `/login`
**File:** `src/views/LoginView.vue`

### Registration
- Name, email, and password fields
- Password confirmation validation
- Auto-login after successful registration
- Link back to login page

**Location:** `/register`
**File:** `src/views/RegisterView.vue`

### Auth Guards
- Protected routes require authentication
- Automatic redirect to login for unauthenticated users
- Token validation on app initialization
- Auto-logout on 401 responses

**Implementation:** `src/router/index.ts`, `src/stores/auth.ts`

## Project Management

### Dashboard
- Grid display of all user projects
- Project cards showing:
  - Project name
  - Description
  - Review question
  - Article count
  - Creation date
- Click card to navigate to project
- Create new project button
- Empty state for users with no projects

**Location:** `/`
**File:** `src/views/DashboardView.vue`
**Components:** `src/components/projects/ProjectCard.vue`

### Create Project
- Modal dialog for project creation
- Fields:
  - Name (required)
  - Description (optional)
  - Review question (optional)
- Form validation
- Success feedback
- Auto-refresh project list

**Component:** `src/components/projects/CreateProjectDialog.vue`

### Project Overview
- View and edit project details
- Upload RIS files for article import
- Project statistics (article count)
- Delete project with confirmation
- Edit mode with save/cancel actions

**Location:** `/projects/:id`
**File:** `src/views/ProjectOverview.vue`

### Project Navigation
- Tabbed interface with:
  - Overview
  - Criteria
  - Articles
  - Screening
- Persistent tab state in URL
- Breadcrumb navigation

**File:** `src/views/ProjectView.vue`

## Criteria Management

### Criteria View
- Split-panel design:
  - Inclusion criteria (left, green)
  - Exclusion criteria (right, red)
- Each criterion shows:
  - Code (I1, E1, etc.)
  - Description
  - Rationale
  - Active/inactive status
- Add button for each type
- Edit and delete actions per criterion

**Location:** `/projects/:id/criteria`
**File:** `src/views/CriteriaView.vue`

### Add/Edit Criterion
- Modal dialog form
- Fields:
  - Description (required)
  - Rationale (optional)
- Type automatically set based on context
- Validation and error handling

**Component:** `src/components/criteria/CriterionForm.vue`

### Criterion Card
- Visual display of criterion details
- Badge showing code and type
- Inactive indicator
- Quick edit/delete actions

**Component:** `src/components/criteria/CriterionCard.vue`

## Article Management

### Articles List
- Table view of all articles
- Display columns:
  - Title
  - Authors (truncated with "et al.")
  - Year and journal
  - Status badge
  - Decision badge
  - Abstract preview (2 lines)
- Click row to view full article details

**Location:** `/projects/:id/articles`
**File:** `src/views/ArticlesView.vue`

### Filtering
- Filter by article status:
  - All, Imported, Screening, Awaiting Full Text, etc.
- Filter by final decision:
  - All, Pending, Included, Excluded
- Clear filters button
- Auto-reset to page 1 on filter change

**Implementation:** `src/views/ArticlesView.vue`

### Pagination
- Page navigation (Previous/Next)
- Current page and total pages display
- Total article count
- Configurable items per page (default: 20)

**Implementation:** `src/stores/articles.ts`, `src/views/ArticlesView.vue`

### Article Detail
- Full article metadata:
  - Complete title
  - All authors
  - Year, journal, DOI, PMID
  - Full abstract
  - Keywords
- Status and decision badges
- Screening history with:
  - Decision type and stage
  - Reasoning
  - Confidence score
  - Source (human/AI)
  - Timestamp
- Back to articles list button

**Location:** `/projects/:id/articles/:articleId`
**File:** `src/views/ArticleDetailView.vue`

## Screening Interface

### Screening View
- One-article-at-a-time workflow
- Article display:
  - Full title
  - Authors
  - Abstract
  - Keywords
  - Year and journal
- Criteria reference panels:
  - Inclusion criteria (left)
  - Exclusion criteria (right)
- Progress statistics:
  - Total articles
  - Screened count
  - Included count
  - Excluded count
  - Uncertain count

**Location:** `/projects/:id/screening`
**File:** `src/views/ScreeningView.vue`

### Decision Panel
- Reasoning textarea for notes
- Three decision buttons:
  - **Include** (green) - Keyboard: I
  - **Exclude** (red) - Keyboard: E
  - **Uncertain** (yellow) - Keyboard: U
- Keyboard shortcut hints
- Loading state during submission
- Auto-advance to next article

**Implementation:** `src/views/ScreeningView.vue`

### Keyboard Shortcuts
- **I** - Mark as Include
- **E** - Mark as Exclude
- **U** - Mark as Uncertain
- Works even when focus is not on buttons
- Disabled during API submission

**Implementation:** Uses `@vueuse/core` `useMagicKeys`

### Progress Tracking
- Real-time statistics update
- Visual progress indicators
- Completion state handling
- "No more articles" message

**Implementation:** `src/stores/screening.ts`

## Technical Features

### State Management (Pinia)
Five specialized stores:
1. **Auth Store** - User session and token management
2. **Projects Store** - CRUD operations for projects
3. **Articles Store** - Article listing and filtering
4. **Criteria Store** - Criteria management with computed lists
5. **Screening Store** - Screening workflow and decisions

**Location:** `src/stores/`

### API Integration
- Centralized API composable
- Axios-based with interceptors
- Automatic JWT token injection
- 401 response handling
- Type-safe method signatures
- Form data support for file uploads

**Location:** `src/composables/useApi.ts`

### Type Safety
Complete TypeScript coverage:
- All API models typed
- Props and emits explicitly typed
- Computed properties with return types
- No `any` types in business logic
- Strict TypeScript configuration

**Location:** `src/types/index.ts`

### Routing
- Hash-based routing for SPA behavior
- Auth guards on protected routes
- Query parameter preservation
- Nested routes for project tabs
- Redirect after login

**Location:** `src/router/index.ts`

### UI Components
Custom component library built with Tailwind:
- Button (variants: default, destructive, outline, ghost, link)
- Card (consistent shadows and borders)
- Input (text, email, password, file)
- Textarea (auto-sizing)
- Label (accessibility-ready)
- Badge (variants: default, secondary, destructive, outline)
- Dialog (modal with overlay and click-outside)
- Select (styled dropdown)
- Tabs (with trigger and content)

**Location:** `src/components/ui/`

### Layout System
- Responsive layout wrapper
- Sticky header with navigation
- Container max-width management
- Consistent spacing and padding

**Components:**
- `src/components/layout/AppHeader.vue`
- `src/components/layout/AppLayout.vue`

### Styling
- Tailwind CSS with custom theme
- CSS variables for colors
- Dark mode support (prepared)
- Consistent spacing scale
- Responsive breakpoints

**Configuration:** `tailwind.config.js`, `src/assets/index.css`

### Developer Experience
- Hot Module Replacement (HMR)
- TypeScript intellisense
- Component prop validation
- Console error messages
- Loading and error states
- Form validation feedback

## Future Enhancements

### Planned Features
1. **Drag-and-drop criteria reordering** - VueUse sortable integration
2. **AI-assisted screening** - Display AI suggestions alongside human decisions
3. **Bulk operations** - Multi-select articles for batch actions
4. **Export functionality** - Download results as CSV/Excel
5. **Team collaboration** - Multi-reviewer support with conflict resolution
6. **Advanced filters** - Search by keywords, authors, date ranges
7. **Data visualization** - Charts for screening progress and statistics
8. **Dark mode toggle** - User preference with persistence
9. **Accessibility improvements** - Screen reader optimization, ARIA labels
10. **Mobile responsiveness** - Touch-optimized interface

### Technical Improvements
1. **Testing** - Vitest unit tests, Playwright e2e tests
2. **Performance** - Virtual scrolling for large article lists
3. **Offline support** - Service worker for PWA functionality
4. **Real-time updates** - WebSocket integration for live collaboration
5. **Internationalization** - Multi-language support with vue-i18n

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)
- Mobile browsers (iOS Safari, Chrome Mobile)

## Performance

- Code splitting by route
- Lazy loading of components
- Optimized bundle size
- Efficient re-renders with Vue 3 reactivity
- Minimal dependencies
