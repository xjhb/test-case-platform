import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import MainLayout from '../layouts/MainLayout.vue'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/Login.vue') },
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('../views/Dashboard.vue'),
        meta: { title: '驾驶舱' },
      },
      {
        path: 'projects',
        name: 'projects',
        component: () => import('../views/Projects.vue'),
        meta: { title: '测试项目' },
      },
      {
        path: 'plans',
        name: 'plans',
        component: () => import('../views/Plans.vue'),
        meta: { title: '项目批次' },
      },
      {
        path: 'calendar',
        name: 'calendar',
        component: () => import('../views/Calendar.vue'),
        meta: { title: '测试日历' },
      },
      {
        path: 'requirements',
        name: 'requirements',
        component: () => import('../views/Requirements.vue'),
        meta: { title: '需求管理' },
      },
      {
        path: 'testcases',
        name: 'testcases',
        component: () => import('../views/TestCases.vue'),
        meta: { title: '测试需求' },
      },
      {
        path: 'users',
        name: 'users',
        component: () => import('../views/Users.vue'),
        meta: { title: '外包人员管理', requireAdmin: true },
      },
      {
        path: 'teams',
        name: 'teams',
        component: () => import('../views/Teams.vue'),
        meta: { title: '团队管理', requireAdmin: true },
      },
      {
        path: 'teams/:id/members',
        name: 'team-members',
        component: () => import('../views/TeamMembers.vue'),
        meta: { title: '团队成员', requireAdmin: true },
      },
      {
        path: 'logs',
        name: 'logs',
        component: () => import('../views/Logs.vue'),
        meta: { title: '操作日志', requireAdmin: true },
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('../views/Profile.vue'),
        meta: { title: '个人账户设置' },
      },
      {
        path: 'settings/security',
        name: 'settings-security',
        component: () => import('../views/SecuritySettings.vue'),
        meta: { title: '安全登录', requireAdmin: true },
      },
      {
        path: 'settings/stage',
        name: 'settings-stage',
        component: () => import('../views/StageSettings.vue'),
        meta: { title: '阶段时间配置', requireAdmin: true },
      },
      {
        path: 'defects',
        name: 'defects',
        component: () => import('../views/Defects.vue'),
        meta: { title: '缺陷管理' },
      },
      {
        path: 'reports',
        name: 'reports',
        component: () => import('../views/Reports.vue'),
        meta: { title: '测试报告' },
      },
      {
        path: 'automation',
        name: 'automation',
        component: () => import('../views/Automation.vue'),
        meta: { title: '自动化集成' },
      },
      {
        path: 'integrations',
        name: 'integrations',
        component: () => import('../views/Integrations.vue'),
        meta: { title: '外部工具集成', requireAdmin: true },
      },
      {
        path: 'notifications',
        name: 'notifications',
        component: () => import('../views/Notifications.vue'),
        meta: { title: '我的通知' },
      },
      {
        path: 'testcases/:id/versions',
        name: 'testcase-versions',
        component: () => import('../views/TestCaseVersions.vue'),
        meta: { title: '用例版本历史' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 路由守卫:未登录跳登录页;非admin访问管理页跳转
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.name !== 'login' && !auth.isLoggedIn) {
    return { name: 'login' }
  }
  if (to.name === 'login' && auth.isLoggedIn) {
    return { name: 'projects' }
  }
  if (to.meta.requireAdmin && auth.role !== 'admin') {
    return { name: 'projects' }
  }
})

export default router
