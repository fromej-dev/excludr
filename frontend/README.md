# Excludr Frontend

Vue 3 + TypeScript frontend for the Excludr systematic review platform.

## Tech Stack

- **Vue 3** with Composition API and `<script setup>`
- **TypeScript** for type safety
- **Vite** for fast development and building
- **Vue Router** for navigation
- **Pinia** for state management
- **Tailwind CSS** for styling
- **VueUse** for composable utilities
- **Axios** for API requests

## Prerequisites

- Node.js 18+ and npm/yarn/pnpm
- Backend API running at `http://localhost:8000`

## Installation

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Project Structure

```
src/
├── assets/          # CSS and static assets
├── components/      # Vue components
│   ├── ui/          # Base UI components (Button, Card, etc.)
│   ├── layout/      # Layout components (AppHeader, AppLayout)
│   ├── articles/    # Article-related components
│   ├── criteria/    # Criteria management components
│   ├── projects/    # Project components
│   └── screening/   # Screening interface components
├── composables/     # Reusable composition functions
├── router/          # Vue Router configuration
├── stores/          # Pinia stores
├── types/           # TypeScript type definitions
├── views/           # Page components
├── App.vue          # Root component
└── main.ts          # Application entry point
```

## Features

### Authentication
- User registration and login
- JWT token management
- Protected routes with auth guards

### Project Management
- Create, read, update, delete projects
- Upload RIS files for article import
- Project overview with statistics

### Criteria Management
- Define inclusion and exclusion criteria
- Drag-and-drop reordering (planned)
- Edit and delete criteria

### Article Management
- View all imported articles
- Filter by status and decision
- Pagination for large datasets
- Article detail view with full metadata

### Screening Interface
- One-article-at-a-time screening workflow
- Keyboard shortcuts (I/E/U for Include/Exclude/Uncertain)
- Criteria reference panel
- Progress tracking
- Reasoning notes for decisions

## API Configuration

The frontend proxies API requests to `http://localhost:8000` via Vite's proxy configuration in `vite.config.ts`. All API calls use the `/api/v1` prefix.

## Development

The project follows Vue 3 best practices:

- All components use `<script setup lang="ts">` syntax
- Props and emits are explicitly typed
- Pinia stores use the setup syntax
- VueUse composables for common patterns
- Tailwind CSS for styling with custom theme variables

## Build

```bash
npm run build
```

This creates an optimized production build in the `dist/` directory.
