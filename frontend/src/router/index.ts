import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/RegisterView.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/',
    name: 'dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/projects/:id',
    name: 'project',
    component: () => import('@/views/ProjectView.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'project-overview',
        component: () => import('@/views/ProjectOverview.vue'),
      },
      {
        path: 'criteria',
        name: 'project-criteria',
        component: () => import('@/views/CriteriaView.vue'),
      },
      {
        path: 'articles',
        name: 'project-articles',
        component: () => import('@/views/ArticlesView.vue'),
      },
      {
        path: 'articles/:articleId',
        name: 'article-detail',
        component: () => import('@/views/ArticleDetailView.vue'),
      },
      {
        path: 'screening',
        name: 'project-screening',
        component: () => import('@/views/ScreeningView.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Auth guard
router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // Initialize auth state if not already done
  if (!authStore.user && authStore.getToken?.()) {
    await authStore.initialize()
  }

  const requiresAuth = to.meta.requiresAuth !== false

  if (requiresAuth && !authStore.isAuthenticated) {
    next({ name: 'login', query: { redirect: to.fullPath } })
  } else if (!requiresAuth && authStore.isAuthenticated && (to.name === 'login' || to.name === 'register')) {
    next({ name: 'dashboard' })
  } else {
    next()
  }
})

export default router
