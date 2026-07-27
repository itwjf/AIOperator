import { CONFIG } from './config';
import { apiRequest } from './api';

export function handleOAuthCallback() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token');
  if (token) {
    localStorage.setItem(CONFIG.JWT_KEY, token);
    window.history.replaceState({}, document.title, window.location.pathname);
    fetchUserInfo();
  }
}

export async function fetchUserInfo() {
  try {
    const resp = await apiRequest('/api/auth/me');
    if (resp.ok) {
      const user = await resp.json();
      localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(user));
    }
  } catch (e) { /* 静默失败 */ }
}

export function logout() {
  localStorage.removeItem(CONFIG.JWT_KEY);
  localStorage.removeItem(CONFIG.USER_KEY);
  window.location.href = '/login';
}

export function getCurrentUser() {
  const raw = localStorage.getItem(CONFIG.USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

export function isAuthenticated() {
  return !!localStorage.getItem(CONFIG.JWT_KEY);
}
