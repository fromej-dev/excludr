import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useApi } from '@/composables/useApi'

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
    name: 'home',
    component: () => import('@/views/HomeView.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/account',
    name: 'account',
    component: () => import('@/views/AccountView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/admin',
    component: () => import('@/views/admin/AdminView.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
    children: [
      {
        path: '',
        name: 'admin-overview',
        component: () => import('@/views/admin/AdminOverview.vue'),
      },
      {
        path: 'users',
        name: 'admin-users',
        component: () => import('@/views/admin/AdminUsers.vue'),
      },
      {
        path: 'users/:userId',
        name: 'admin-user',
        component: () => import('@/views/admin/AdminUserDetail.vue'),
      },
      {
        path: 'projects',
        name: 'admin-projects',
        component: () => import('@/views/admin/AdminProjects.vue'),
      },
      {
        path: 'payments',
        name: 'admin-payments',
        component: () => import('@/views/admin/AdminPayments.vue'),
      },
    ],
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
        path: 'articles/upload-pdfs',
        name: 'project-pdf-upload',
        component: () => import('@/views/PdfUploadView.vue'),
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
      {
        path: 'members',
        name: 'project-members',
        component: () => import('@/views/MembersView.vue'),
      },
      {
        path: 'conflicts',
        name: 'project-conflicts',
        component: () => import('@/views/ConflictsView.vue'),
      },
      {
        path: 'reports',
        name: 'project-reports',
        component: () => import('@/views/ReportsView.vue'),
      },
      {
        path: 'audit',
        name: 'project-audit',
        component: () => import('@/views/AuditView.vue'),
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  // Lets the public header's section links (/#features) land on their section from any page
  scrollBehavior(to, _from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.hash) return { el: to.hash, behavior: 'smooth' }
  },
})

// Auth guard
router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()
  const { getToken } = useApi()

  // Initialize auth state if not already done
  if (!authStore.user && getToken()) {
    await authStore.initialize()
  }

  const requiresAuth = to.meta.requiresAuth !== false

  if (requiresAuth && !authStore.isAuthenticated) {
    next({ name: 'login', query: { redirect: to.fullPath } })
  } else if (to.matched.some((r) => r.meta.requiresAdmin) && !authStore.user?.is_superuser) {
    next({ name: 'dashboard' })
  } else if (!requiresAuth && authStore.isAuthenticated && (to.name === 'login' || to.name === 'register')) {
    next({ name: 'dashboard' })
  } else {
    next()
  }
})

export default router
