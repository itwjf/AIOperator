<template>
  <div class="login-page">
    <div class="login-card">
      <h1>AIOperator</h1>
      <p class="subtitle">AI 智能运维助手</p>
      <a href="/api/auth/github/login" class="github-btn">
        <svg viewBox="0 0 16 16" class="github-icon">
          <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
        </svg>
        使用 GitHub 登录
      </a>
      <p class="footer-text">登录即表示你同意将 GitHub 账号信息用于身份认证</p>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue';
import { handleOAuthCallback } from '../utils/auth';

onMounted(() => handleOAuthCallback());
</script>

<style scoped>
* { margin: 0; padding: 0; box-sizing: border-box; }

.login-page {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d1117 100%);
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}

.login-card {
  background: rgba(22, 27, 34, 0.85);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  padding: 48px 40px;
  width: 400px;
  max-width: 90vw;
  text-align: center;
}

.login-card h1 { color: #e6edf3; font-size: 28px; font-weight: 600; margin-bottom: 8px; }
.subtitle { color: #8b949e; font-size: 14px; margin-bottom: 40px; }

.github-btn {
  display: inline-flex; align-items: center; gap: 10px;
  background: #24292f; color: #fff;
  border: 1px solid rgba(255,255,255,0.15); border-radius: 8px;
  padding: 12px 32px; font-size: 16px; font-weight: 500;
  cursor: pointer; text-decoration: none;
  transition: background 0.2s, border-color 0.2s;
}
.github-btn:hover { background: #2c333a; border-color: rgba(255,255,255,0.25); }
.github-icon { width: 20px; height: 20px; fill: currentColor; }
.footer-text { color: #484f58; font-size: 12px; margin-top: 32px; }
</style>
