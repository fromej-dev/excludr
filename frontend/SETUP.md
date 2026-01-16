# Excludr Frontend Setup Guide

## Quick Start

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Ensure Backend is Running

The backend API must be running at `http://localhost:8000`. From the project root:

```bash
# Install backend dependencies (if not already done)
uv sync

# Run migrations
alembic upgrade head

# Start the backend server
uvicorn app.main:app --reload
```

### 3. Start the Frontend Development Server

```bash
npm run dev
```

The frontend will be available at `http://localhost:5173` (or the next available port).

## Complete File Structure

```
frontend/
├── src/
│   ├── assets/
│   │   └── index.css                 # Tailwind CSS with theme variables
│   ├── components/
│   │   ├── ui/                       # Base UI components
│   │   │   ├── Badge.vue
│   │   │   ├── Button.vue
│   │   │   ├── Card.vue
│   │   │   ├── Dialog.vue
│   │   │   ├── Input.vue
│   │   │   ├── Label.vue
│   │   │   ├── Select.vue
│   │   │   ├── Tabs.vue
│   │   │   ├── TabsContent.vue
│   │   │   ├── TabsList.vue
│   │   │   ├── TabsTrigger.vue
│   │   │   └── Textarea.vue
│   │   ├── layout/
│   │   │   ├── AppHeader.vue         # Top navigation bar
│   │   │   └── AppLayout.vue         # Main layout wrapper
│   │   ├── articles/                 # (Reserved for future components)
│   │   ├── criteria/
│   │   │   ├── CriterionCard.vue     # Individual criterion display
│   │   │   └── CriterionForm.vue     # Add/edit criterion dialog
│   │   └── projects/
│   │       ├── ProjectCard.vue       # Project card for dashboard
│   │       └── CreateProjectDialog.vue
│   ├── composables/
│   │   └── useApi.ts                 # Axios wrapper with auth
│   ├── router/
│   │   └── index.ts                  # Vue Router with auth guards
│   ├── stores/
│   │   ├── auth.ts                   # Authentication state
│   │   ├── projects.ts               # Projects CRUD
│   │   ├── articles.ts               # Articles and stats
│   │   ├── criteria.ts               # Criteria management
│   │   └── screening.ts              # Screening workflow
│   ├── types/
│   │   └── index.ts                  # All TypeScript interfaces
│   ├── views/
│   │   ├── LoginView.vue             # Login page
│   │   ├── RegisterView.vue          # Registration page
│   │   ├── DashboardView.vue         # Projects dashboard
│   │   ├── ProjectView.vue           # Project layout with tabs
│   │   ├── ProjectOverview.vue       # Project overview tab
│   │   ├── CriteriaView.vue          # Criteria management tab
│   │   ├── ArticlesView.vue          # Articles list tab
│   │   ├── ArticleDetailView.vue     # Individual article view
│   │   └── ScreeningView.vue         # Screening interface tab
│   ├── App.vue                       # Root component
│   ├── main.ts                       # Application entry point
│   └── vite-env.d.ts                 # TypeScript declarations
├── index.html                        # HTML entry point
├── package.json                      # Dependencies
├── tsconfig.json                     # TypeScript config
├── tsconfig.node.json                # TypeScript config for Node
├── vite.config.ts                    # Vite config with proxy
├── tailwind.config.js                # Tailwind CSS config
├── postcss.config.js                 # PostCSS config
├── .gitignore                        # Git ignore rules
├── README.md                         # Documentation
└── SETUP.md                          # This file
```

## Key Features

### Authentication Flow
1. User lands on login page (`/login`)
2. After successful login, JWT token is stored in localStorage
3. Auth guard redirects to dashboard (`/`)
4. Token is automatically added to all API requests
5. On 401 response, user is logged out and redirected to login

### Project Workflow
1. **Dashboard** - View all projects, create new ones
2. **Project Overview** - Edit project details, upload RIS files
3. **Criteria** - Define inclusion/exclusion criteria
4. **Articles** - Browse imported articles with filters
5. **Screening** - Screen articles one by one with keyboard shortcuts

### API Integration
All API calls go through the `useApi` composable:
- Base URL: `/api/v1` (proxied to `http://localhost:8000`)
- JWT token automatically included in headers
- 401 responses trigger logout

### State Management
Pinia stores handle all state:
- `authStore` - User session
- `projectsStore` - Projects CRUD
- `articlesStore` - Articles and pagination
- `criteriaStore` - Criteria management
- `screeningStore` - Screening workflow

## Development Tips

### Hot Module Replacement
Vite provides instant HMR for Vue components. Changes appear immediately without full page reload.

### Type Safety
All components use TypeScript with strict typing. The IDE will provide autocomplete and type checking.

### Debugging
Vue DevTools browser extension is highly recommended for debugging components and Pinia stores.

### API Proxy
The Vite dev server proxies `/api` requests to `http://localhost:8000`. No CORS issues during development.

## Building for Production

```bash
npm run build
```

This creates an optimized production build in `dist/` directory. Deploy these static files to any web server.

## Troubleshooting

### Port Already in Use
If port 5173 is in use, Vite will automatically use the next available port. Check the terminal output.

### API Connection Refused
Ensure the backend is running at `http://localhost:8000`. Check with:
```bash
curl http://localhost:8000/api/v1/docs
```

### TypeScript Errors
Run type checking:
```bash
npm run build
```

### Module Not Found
Clear node_modules and reinstall:
```bash
rm -rf node_modules package-lock.json
npm install
```
