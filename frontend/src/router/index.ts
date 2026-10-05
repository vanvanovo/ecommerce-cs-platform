import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      component: () => import('@/components/layout/AppLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          redirect: '/dashboard',
        },
        {
          path: 'dashboard',
          name: 'dashboard',
          component: () => import('@/views/DashboardView.vue'),
        },
        // AI 助手（统一入口）
        {
          path: 'chat',
          name: 'chat',
          component: () => import('@/views/UnifiedChatView.vue'),
        },
        // 客服工作台（P6：主管审批 + 未解决问题池，仅主管/管理员）
        {
          path: 'reviews',
          name: 'reviews',
          component: () => import('@/views/ReviewWorkbenchView.vue'),
          meta: { requiresTeacher: true },
        },
        {
          path: 'unresolved',
          name: 'unresolved',
          component: () => import('@/views/UnresolvedPoolView.vue'),
          meta: { requiresTeacher: true },
        },
      ],
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/dashboard',
    },
  ],
})

router.beforeEach((to, _from, next) => {
  const auth = useAuthStore()

  if (to.meta.public) {
    if (auth.isLoggedIn && to.name === 'login') return next('/dashboard')
    return next()
  }

  if (!auth.isLoggedIn) return next('/login')

  if (to.meta.requiresTeacher && !auth.isTeacher) return next('/dashboard')

  next()
})

export default router
