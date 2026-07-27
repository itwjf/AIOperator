import { CONFIG } from './config';

export async function apiRequest(path, options = {}) {
  const token = localStorage.getItem(CONFIG.JWT_KEY);
  const isFormData = options.body instanceof FormData;
  const headers = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(options.headers || {}),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(path, { ...options, headers });

  if (response.status === 401) {
    localStorage.removeItem(CONFIG.JWT_KEY);
    localStorage.removeItem(CONFIG.USER_KEY);
    window.location.href = '/login';
    throw new Error('登录已过期，请重新登录');
  }

  return response;
}
