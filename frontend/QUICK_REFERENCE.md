# Quick Reference Guide

## Installation & Setup

```bash
cd frontend
npm install
npm run dev
```

The app will be available at http://localhost:5173

## Project Structure Quick Reference

```
src/
├── views/           # Page components (routes)
├── components/      # Reusable components
│   ├── ui/          # Base components (Button, Card, etc.)
│   ├── layout/      # Layout wrappers
│   ├── projects/    # Project-specific
│   └── criteria/    # Criteria-specific
├── stores/          # Pinia state management
├── router/          # Vue Router config
├── composables/     # Reusable logic
├── types/           # TypeScript types
└── assets/          # CSS and static files
```

## Key Files

| File                          | Purpose                          |
|-------------------------------|----------------------------------|
| `src/main.ts`                 | App entry point                  |
| `src/App.vue`                 | Root component                   |
| `src/router/index.ts`         | Routes and auth guards           |
| `src/composables/useApi.ts`   | API client with auth             |
| `src/types/index.ts`          | All TypeScript interfaces        |
| `vite.config.ts`              | Vite config + API proxy          |
| `tailwind.config.js`          | Tailwind theme                   |

## Common Tasks

### Adding a New Page

1. Create view in `src/views/MyView.vue`
2. Add route in `src/router/index.ts`
3. Add navigation link if needed

### Creating a New Component

```vue
<script setup lang="ts">
// 1. Type imports
import type { MyType } from '@/types'

// 2. Component imports
import Button from '@/components/ui/Button.vue'

// 3. Props definition
interface Props {
  title: string
  count?: number
}

const props = defineProps<Props>()

// 4. Emits definition
const emit = defineEmits<{
  'click': [id: number]
}>()

// 5. State and logic
import { ref } from 'vue'
const isOpen = ref(false)
</script>

<template>
  <div>
    <!-- Your template -->
  </div>
</template>
```

### Adding a New API Endpoint

1. Add types to `src/types/index.ts`
2. Add store method in appropriate store
3. Use in component with store

Example:
```typescript
// In store
const fetchSomething = async () => {
  loading.value = true
  try {
    const data = await get<MyType>('/endpoint')
    // handle data
  } catch (err) {
    error.value = 'Error message'
  } finally {
    loading.value = false
  }
}
```

### Using a Store in a Component

```vue
<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

// Access state
const user = authStore.user

// Call actions
authStore.login(credentials)
</script>
```

## Component Patterns

### Form Component

```vue
<script setup lang="ts">
import { ref } from 'vue'
import Button from '@/components/ui/Button.vue'
import Input from '@/components/ui/Input.vue'

const formData = ref({
  name: '',
  email: '',
})

const handleSubmit = () => {
  // Handle form submission
}
</script>

<template>
  <form @submit.prevent="handleSubmit">
    <Input v-model="formData.name" />
    <Button type="submit">Submit</Button>
  </form>
</template>
```

### Dialog Component

```vue
<script setup lang="ts">
import { ref } from 'vue'
import Dialog from '@/components/ui/Dialog.vue'
import Button from '@/components/ui/Button.vue'

const isOpen = ref(false)
</script>

<template>
  <Button @click="isOpen = true">Open Dialog</Button>
  <Dialog v-model:open="isOpen" title="My Dialog">
    <!-- Dialog content -->
  </Dialog>
</template>
```

### List with Loading State

```vue
<script setup lang="ts">
import { onMounted } from 'vue'
import { useProjectsStore } from '@/stores/projects'

const projectsStore = useProjectsStore()

onMounted(() => {
  projectsStore.fetchProjects()
})
</script>

<template>
  <div v-if="projectsStore.loading">Loading...</div>
  <div v-else-if="projectsStore.error">{{ projectsStore.error }}</div>
  <div v-else>
    <div v-for="project in projectsStore.projects" :key="project.id">
      {{ project.name }}
    </div>
  </div>
</template>
```

## Styling Quick Reference

### Tailwind Utilities

```html
<!-- Layout -->
<div class="flex items-center justify-between gap-4">
<div class="grid grid-cols-2 gap-6">

<!-- Spacing -->
<div class="p-4 m-2">        <!-- padding/margin: 16px/8px -->
<div class="px-6 py-3">      <!-- padding x/y -->
<div class="space-y-4">      <!-- gap between children -->

<!-- Typography -->
<h1 class="text-3xl font-bold">
<p class="text-sm text-muted-foreground">

<!-- Colors -->
<div class="bg-primary text-primary-foreground">
<div class="bg-destructive text-destructive-foreground">

<!-- Borders & Radius -->
<div class="border rounded-md">
<div class="border-b border-border">

<!-- Interactive -->
<button class="hover:bg-accent focus:ring-2 focus:ring-ring">
```

### Custom Theme Colors

Use these semantic color classes:
- `bg-background` / `text-foreground`
- `bg-primary` / `text-primary-foreground`
- `bg-secondary` / `text-secondary-foreground`
- `bg-destructive` / `text-destructive-foreground`
- `bg-muted` / `text-muted-foreground`
- `bg-accent` / `text-accent-foreground`
- `border-border` / `border-input`

## API Integration

### Basic GET Request

```typescript
import { useApi } from '@/composables/useApi'

const { get } = useApi()

const data = await get<MyType>('/endpoint')
```

### POST with Body

```typescript
const { post } = useApi()

const result = await post<ResponseType>('/endpoint', {
  name: 'value',
})
```

### File Upload

```typescript
const { post } = useApi()

const formData = new FormData()
formData.append('file', file)

const result = await post('/upload', formData, {
  headers: { 'Content-Type': 'multipart/form-data' }
})
```

## Routing

### Navigation

```vue
<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

const goToProject = (id: number) => {
  router.push({ name: 'project', params: { id } })
}
</script>

<template>
  <router-link to="/">Home</router-link>
  <router-link :to="{ name: 'project', params: { id: 1 } }">
    Project 1
  </router-link>
</template>
```

### Route Parameters

```vue
<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
const projectId = route.params.id
</script>
```

## VueUse Composables

Common VueUse utilities used in the project:

```typescript
import {
  onClickOutside,  // Click outside element
  useMagicKeys,    // Keyboard shortcuts
  useStorage,      // localStorage reactive
} from '@vueuse/core'

// Click outside
const target = ref(null)
onClickOutside(target, () => { /* handle */ })

// Keyboard shortcuts
const { i, e, escape } = useMagicKeys()
watch(i, (pressed) => { if (pressed) handleInclude() })

// Persistent storage
const settings = useStorage('app-settings', { theme: 'light' })
```

## TypeScript Tips

### Typing Props

```typescript
interface Props {
  required: string
  optional?: number
  withDefault?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  withDefault: true
})
```

### Typing Emits

```typescript
const emit = defineEmits<{
  'update:modelValue': [value: string]
  'submit': [id: number, data: FormData]
}>()

emit('submit', 123, formData)
```

### Typing Computed

```typescript
import { computed, type ComputedRef } from 'vue'

const filtered: ComputedRef<Article[]> = computed(() => {
  return articles.value.filter(a => a.status === 'pending')
})
```

## Debugging

### Vue DevTools
Install the Vue DevTools browser extension to inspect:
- Component hierarchy
- Component state
- Pinia stores
- Router state
- Events

### Console Logging in Development

```typescript
// Component state
console.log('State:', { projects: projectsStore.projects })

// API responses
const data = await get('/endpoint')
console.log('API Response:', data)

// Event handlers
const handleClick = () => {
  console.log('Clicked!')
}
```

### TypeScript Errors

Check types with:
```bash
npm run build
```

## Performance Tips

1. Use `v-show` for frequently toggled elements
2. Use `v-if` for conditionally rendered elements
3. Add `:key` to all `v-for` loops
4. Lazy load routes with `() => import()`
5. Avoid inline functions in templates
6. Use `computed` for derived state

## Common Issues

### Port in Use
If port 5173 is taken, Vite uses the next available port. Check terminal output.

### Cannot Connect to API
Ensure backend is running:
```bash
curl http://localhost:8000/api/v1/docs
```

### Module Not Found
Clear and reinstall:
```bash
rm -rf node_modules package-lock.json
npm install
```

### TypeScript Errors
Restart the TypeScript server in your editor, or run:
```bash
npm run build
```
