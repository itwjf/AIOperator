<template>
  <div class="main-page">
    <Sidebar
      :sessions="sessions"
      :currentSessionId="currentSessionId"
      :collapsed="sidebarCollapsed"
      @new="newSession"
      @switch="switchSession"
      @delete="deleteSession"
      @toggle="sidebarCollapsed = !sidebarCollapsed"
    />
    <main class="main-area">
      <header class="topbar">
        <button class="btn-menu" @click="sidebarCollapsed = !sidebarCollapsed">
          <span class="menu-icon"><span></span><span></span><span></span></span>
        </button>
        <ModeSwitcher v-model="chatMode" @diagnose="startDiagnose" />
        <div class="user-area">
          <span class="user-name">{{ currentUser?.username }}</span>
          <button class="btn-logout" @click="handleLogout">退出</button>
        </div>
      </header>
      <ChatPanel
        ref="chatPanel"
        :sessions="sessions"
        :chatMode="chatMode"
        :currentSessionId="currentSessionId"
        @sessions-changed="loadSessions"
      />
    </main>
    <AIOpsPanel
      v-if="showDiagnosis"
      @confirm="confirmDiagnosis"
      @cancel="showDiagnosis = false"
    />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { apiRequest } from '../utils/api';
import { fetchUserInfo, logout, getCurrentUser } from '../utils/auth';
import Sidebar from '../components/Sidebar.vue';
import ChatPanel from '../components/ChatPanel.vue';
import ModeSwitcher from '../components/ModeSwitcher.vue';
import AIOpsPanel from '../components/AIOpsPanel.vue';

const chatPanel = ref(null);

const sessions = ref([]);
const currentSessionId = ref('default');
const chatMode = ref('chat');
const sidebarCollapsed = ref(false);
const currentUser = ref(getCurrentUser());
const showDiagnosis = ref(false);

async function loadSessions() {
  try {
    const resp = await apiRequest('/api/sessions');
    if (resp.ok) sessions.value = await resp.json();
  } catch (e) { /* API 不可用时降级为默认会话 */ }
}

// 前端 mode 值 → 后端合法 agent_type 的映射
const AGENT_TYPE_MAP = { chat: 'rag', agent: 'manual', mcp: 'mcp', aiops: 'aiops' };

function newSession() {
  const id = 'sess-' + Date.now();
  const agentType = AGENT_TYPE_MAP[chatMode.value] || chatMode.value;
  const title = `会话 ${sessions.value.length + 1}`;
  sessions.value.unshift({ session_id: id, title, agent_type: agentType });
  currentSessionId.value = id;
  chatPanel.value?.clearMessages();
  apiRequest('/api/sessions', {
    method: 'POST',
    body: JSON.stringify({ session_id: id, agent_type: agentType, title }),
  }).catch(() => {});
}

async function switchSession(id) {
  currentSessionId.value = id;
  chatPanel.value?.loadMessages(id);
}

async function deleteSession(id) {
  if (sessions.value.length <= 1) return;
  sessions.value = sessions.value.filter(s => s.session_id !== id);
  if (currentSessionId.value === id) {
    currentSessionId.value = sessions.value[0]?.session_id || 'default';
    chatPanel.value?.loadMessages(currentSessionId.value);
  }
  apiRequest(`/api/sessions/${id}`, { method: 'DELETE' }).catch(() => {});
}

function startDiagnose() {
  showDiagnosis.value = true;
}

function confirmDiagnosis(scope) {
  showDiagnosis.value = false;
  chatMode.value = 'aiops';
  chatPanel.value?.sendDiagnoseMessage(scope);
}

function handleLogout() {
  logout();
}

onMounted(async () => {
  await fetchUserInfo();
  currentUser.value = getCurrentUser();
  loadSessions();
});
</script>

<style>
:root {
  --bg-base: #F5F5F7;
  --sidebar-bg: rgba(255,255,255,0.88);
  --sidebar-text: #1A1A1A;
  --sidebar-border: rgba(0,0,0,0.06);
  --accent: #2563EB;
  --text: #1A1A1A;
  --text-secondary: #6B6B6B;
  --radius: 14px;
  --radius-lg: 20px;
  --shadow-md: 0 4px 16px rgba(0,0,0,0.07);
  --glass-border: rgba(0,0,0,0.06);
  --transition: 280ms ease;
  --sidebar-width: 280px;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* 主应用全屏布局 — overflow:hidden 由 msg-list 内部 scroll 替代 */
body {
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: var(--bg-base); color: var(--text); height: 100vh; overflow: hidden;
}

.main-page { display: flex; height: 100vh; }
.main-area { flex: 1; display: flex; flex-direction: column; min-width: 0; }

.topbar {
  height: 60px; display: flex; align-items: center; gap: 16px;
  padding: 0 24px; border-bottom: 1px solid var(--sidebar-border);
  background: rgba(255,255,255,0.65); backdrop-filter: blur(20px);
}

.btn-menu {
  width: 36px; height: 36px; border: none; background: none; cursor: pointer;
  display: flex; align-items: center; justify-content: center; border-radius: 8px;
}
.btn-menu:hover { background: rgba(0,0,0,0.04); }
.menu-icon { display: flex; flex-direction: column; gap: 4px; }
.menu-icon span { display: block; width: 18px; height: 2px; background: var(--text); border-radius: 1px; }

.user-area { margin-left: auto; display: flex; align-items: center; gap: 12px; }
.user-name { font-size: 14px; color: var(--text-secondary); }
.btn-logout {
  padding: 6px 14px; border: 1px solid var(--sidebar-border); border-radius: 8px;
  background: #fff; font-size: 13px; cursor: pointer; color: var(--text-secondary);
}
.btn-logout:hover { background: rgba(0,0,0,0.04); }
</style>
