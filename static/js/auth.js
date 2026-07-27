// AIOperator 认证模块 — GitHub OAuth 登录 + Token 管理
function handleOAuthCallback() {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    if (token) {
        localStorage.setItem(CONFIG.JWT_KEY, token);
        window.history.replaceState({}, document.title, window.location.pathname);
        fetchUserInfo();
    }
}

async function fetchUserInfo() {
    try {
        const resp = await apiRequest('/api/auth/me');
        if (resp.ok) {
            const user = await resp.json();
            localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(user));
        }
    } catch (e) {
        // 静默失败
    }
}

function logout() {
    localStorage.removeItem(CONFIG.JWT_KEY);
    localStorage.removeItem(CONFIG.USER_KEY);
    window.location.href = '/static/login.html';
}

function getCurrentUser() {
    const raw = localStorage.getItem(CONFIG.USER_KEY);
    return raw ? JSON.parse(raw) : null;
}

// 页面加载时检查是否有 OAuth 回调 token
if (window.location.search.includes('token=')) {
    handleOAuthCallback();
}
