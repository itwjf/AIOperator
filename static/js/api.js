// AIOperator HTTP 封装 — 自动注入 JWT，处理 401
async function apiRequest(path, options = {}) {
    const token = localStorage.getItem(CONFIG.JWT_KEY);
    const headers = {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
    };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(path, { ...options, headers });

    if (response.status === 401) {
        localStorage.removeItem(CONFIG.JWT_KEY);
        localStorage.removeItem(CONFIG.USER_KEY);
        if (!window.location.pathname.endsWith('login.html')) {
            window.location.href = '/static/login.html';
        }
        throw new Error('登录已过期，请重新登录');
    }

    return response;
}
