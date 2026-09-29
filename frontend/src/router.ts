import { createRouter, createWebHistory } from 'vue-router'
import { getToken } from './api'

const routes = [
  { path: '/login', component: () => import('./pages/Login.vue') },
  { path: '/', component: () => import('./pages/Dashboard.vue') },
  { path: '/payments', component: () => import('./pages/Payments.vue') },
  { path: '/transfer', redirect: '/payments' },
  { path: '/cashback', redirect: '/cards' },
  { path: '/webhooks', redirect: '/' },
  { path: '/exchange', component: () => import('./pages/Exchange.vue') },
  { path: '/cards', component: () => import('./pages/Cards.vue') },
  { path: '/accounts', component: () => import('./pages/Accounts.vue') },
  { path: '/statements', component: () => import('./pages/Statements.vue') },
  { path: '/profile', component: () => import('./pages/Profile.vue') },

  { path: '/backoffice', component: () => import('./pages/Backoffice.vue') },
  { path: '/tasks', component: () => import('./pages/Progress.vue') },
  { path: '/progress', redirect: '/tasks' },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.path !== '/login' && to.path !== '/tasks' && !getToken()) {
    return '/login'
  }
  return true
})
