/**
 * AIOperator 前端 — Vue 3 应用
 *
 * 功能：
 *  - 四种对话模式（chat / agent / aiops / mcp）
 *  - SSE 流式消费（fetch + ReadableStream）
 *  - Markdown 渲染 + 代码高亮
 *  - 会话管理（localStorage）
 */

const { createApp, ref, reactive, computed, watch, nextTick, onMounted } = Vue;

// === marked.js 配置 ===
marked.setOptions({ breaks: true, gfm: true });

function renderMarkdown(text) {
  if (!text) return '';
  const html = marked.parse(text);
  return html;
}

// === 会话持久化 ===
const STORAGE_KEY = 'aioperator_sessions';

function loadSessions() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (e) { /* ignore */ }
  return [{ id: 'default', name: '默认会话' }];
}

function saveSessions(sessions) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

// === Vue 应用 ===
const app = createApp({
  setup() {
    // --- 状态 ---
    const sessions = ref(loadSessions());
    const currentSessionId = ref(sessions.value[0]?.id || 'default');
    const messages = ref([]);          // { role, html, toolCalls, aiopsPlan, ... }
    const input = ref('');
    const loading = ref(false);
    const useStream = ref(true);
    const chatMode = ref('chat');
    const sidebarCollapsed = ref(false);

    const msgContainer = ref(null);
    const inputBox = ref(null);

    // --- 会话 ---
    function newSession() {
      const name = `会话 ${sessions.value.length + 1}`;
      const id = 'sess-' + Date.now();
      sessions.value.push({ id, name });
      currentSessionId.value = id;
      messages.value = [];
      saveSessions(sessions.value);
    }

    function switchSession(id) {
      currentSessionId.value = id;
      messages.value = loadMessages(id);
    }

    function deleteSession(id) {
      if (sessions.value.length <= 1) return;
      const idx = sessions.value.findIndex(s => s.id === id);
      if (idx !== -1) {
        sessions.value.splice(idx, 1);
        if (currentSessionId.value === id) {
          currentSessionId.value = sessions.value[0].id;
          messages.value = loadMessages(sessions.value[0].id);
        }
        saveSessions(sessions.value);
      }
    }

    watch(sessions, s => saveSessions(s), { deep: true });

    // --- 消息持久化（按会话） ---
    const MSG_PREFIX = 'aioperator_msgs_';

    function loadMessages(sid) {
      try {
        const raw = localStorage.getItem(MSG_PREFIX + sid);
        return raw ? JSON.parse(raw) : [];
      } catch (e) { return []; }
    }

    function persistMessages() {
      localStorage.setItem(
        MSG_PREFIX + currentSessionId.value,
        JSON.stringify(messages.value.slice(-50)) // 最多保存 50 条
      );
    }

    watch(messages, () => persistMessages(), { deep: true });

    // 切会话时恢复消息
    watch(currentSessionId, sid => {
      messages.value = loadMessages(sid);
      nextTick(() => scrollBottom());
    });

    // 初始加载
    messages.value = loadMessages(currentSessionId.value);

    // --- 滚动 ---
    function scrollBottom() {
      nextTick(() => {
        const el = msgContainer.value;
        if (el) el.scrollTop = el.scrollHeight;
      });
    }

    // --- 调 API ---
    const API_BASE = '';

    function getApiUrl() {
      const map = {
        chat: '/api/chat',
        agent: '/api/agent/chat',
        mcp: '/api/mcp/chat',
      };
      const base = map[chatMode.value] || '/api/chat';
      return useStream.value ? base + '_stream' : base;
    }

    async function sendMessage() {
      const text = input.value.trim();
      if (!text || loading.value) return;
      input.value = '';

      // 添加用户消息
      messages.value.push({ role: 'user', html: renderMarkdown(text) });
      scrollBottom();
      loading.value = true;

      // AIOps 诊断模式 — 特殊处理
      if (chatMode.value === 'aiops') {
        await runAIOps();
        return;
      }

      if (useStream.value) {
        await runStreamChat(text, getApiUrl());
      } else {
        await runNonStreamChat(text, getApiUrl());
      }
    }

    // --- 非流式 ---
    async function runNonStreamChat(question, url) {
      try {
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question, session_id: currentSessionId.value }),
        });
        const data = await res.json();
        messages.value.push({ role: 'assistant', html: renderMarkdown(data.answer) });
      } catch (e) {
        messages.value.push({ role: 'assistant', html: `<em>请求失败：${e.message}</em>` });
      } finally {
        loading.value = false;
        scrollBottom();
      }
    }

    // --- 流式（SSE via fetch） ---
    async function runStreamChat(question, url) {
      const msg = { role: 'assistant', html: '', toolCalls: [] };
      messages.value.push(msg);

      let buffer = '';

      try {
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question, session_id: currentSessionId.value }),
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let leftover = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          leftover += chunk;
          const lines = leftover.split('\n');
          leftover = lines.pop() || '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === 'content') {
                buffer += event.data;
                msg.html = renderMarkdown(buffer);
                scrollBottom();
              } else if (event.type === 'tool_start') {
                if (!msg.toolCalls.includes(event.data)) {
                  msg.toolCalls.push(event.data);
                }
              } else if (event.type === 'done') {
                // 最终渲染 + 代码高亮
                msg.html = renderMarkdown(buffer);
                nextTick(() => highlightCode());
              } else if (event.type === 'error') {
                msg.html = renderMarkdown(`**出错：** ${event.data}`);
              }
            } catch (e) { /* 跳过解析失败的行 */ }
          }
        }
      } catch (e) {
        msg.html = renderMarkdown(`**连接失败：** ${e.message}`);
      } finally {
        loading.value = false;
        scrollBottom();
        nextTick(() => highlightCode());
      }
    }

    // --- AIOps 诊断 ---
    function startAIOps() {
      chatMode.value = 'aiops';
      messages.value.push({ role: 'user', html: renderMarkdown('🔍 启动系统全面诊断…') });
      scrollBottom();
      loading.value = true;
      runAIOps();
    }

    async function runAIOps() {
      const msg = {
        role: 'assistant',
        html: '',
        toolCalls: [],
        aiopsPlan: [],
        aiopsResults: {},
        aiopsCurrent: -1,
      };
      messages.value.push(msg);

      let reportBuffer = '';

      try {
        const res = await fetch('/api/aiops', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: currentSessionId.value }),
        });

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let leftover = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          leftover += decoder.decode(value, { stream: true });
          const lines = leftover.split('\n');
          leftover = lines.pop() || '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const event = JSON.parse(line.slice(6));

              if (event.type === 'plan') {
                msg.aiopsPlan = event.data.steps;
                msg.html = '<em>正在执行诊断计划…</em>';
                scrollBottom();
              } else if (event.type === 'step_start') {
                const idx = msg.aiopsPlan.indexOf(event.data);
                if (idx !== -1) msg.aiopsCurrent = idx;
                scrollBottom();
              } else if (event.type === 'step_result') {
                const idx = msg.aiopsPlan.indexOf(event.data.step);
                if (idx !== -1) msg.aiopsResults[idx] = event.data.result;
                scrollBottom();
              } else if (event.type === 'replan') {
                msg.aiopsPlan = event.data.new_plan;
                msg.aiopsResults = {};
                msg.aiopsCurrent = -1;
                msg.html = '<em>🔄 计划已调整，继续执行…</em>';
                scrollBottom();
              } else if (event.type === 'report') {
                reportBuffer = event.data;
                msg.html = renderMarkdown(reportBuffer);
                nextTick(() => highlightCode());
                scrollBottom();
              } else if (event.type === 'done') {
                // 完成
              } else if (event.type === 'error') {
                msg.html = renderMarkdown(`**诊断出错：** ${event.data}`);
              }
            } catch (e) { /* skip */ }
          }
        }
      } catch (e) {
        msg.html = renderMarkdown(`**连接失败：** ${e.message}`);
      } finally {
        loading.value = false;
        scrollBottom();
        nextTick(() => highlightCode());
      }
    }

    // --- 代码高亮 ---
    function highlightCode() {
      document.querySelectorAll('.msg-content pre code').forEach(block => {
        hljs.highlightElement(block);
      });
    }

    // --- 文件上传 ---
    async function uploadFile(e) {
      const file = e.target.files[0];
      if (!file) return;

      const form = new FormData();
      form.append('file', file);

      try {
        const res = await fetch('/api/upload', { method: 'POST', body: form });
        const data = await res.json();
        messages.value.push({
          role: 'assistant',
          html: renderMarkdown(`✅ **上传成功** — \`${data.filename}\`，${data.chunks} 个分片已入库。`),
        });
        scrollBottom();
      } catch (err) {
        messages.value.push({
          role: 'assistant',
          html: renderMarkdown(`❌ **上传失败** — ${err.message}`),
        });
      }
      e.target.value = '';
    }

    // --- 生命周期 ---
    onMounted(() => {
      inputBox.value?.focus();
    });

    return {
      sessions, currentSessionId, messages, input, loading,
      useStream, chatMode, sidebarCollapsed,
      msgContainer, inputBox,
      newSession, switchSession, deleteSession,
      sendMessage, startAIOps, uploadFile,
    };
  },
});

app.mount('#app');
