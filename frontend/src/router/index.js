import { createRouter, createWebHistory } from 'vue-router';
import { isAuthenticated } from '../utils/auth';
import LoginPage from '../pages/LoginPage.vue';
import MainPage from '../pages/MainPage.vue';

const routes = [
  { path: '/login', name: 'Login', component: LoginPage },
  { path: '/', name: 'Main', component: MainPage, meta: { requiresAuth: true } },
];

const router = createRouter({ history: createWebHistory(), routes });

router.beforeEach((to, from, next) => {
  if (to.meta.requiresAuth && !isAuthenticated()) {
    next('/login');
  } else if (to.path === '/login' && isAuthenticated()) {
    next('/');
  } else {
    next();
  }
});

export default router;
