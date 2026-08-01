<template>
  <div class="chat-container">
    <div class="msg-list" ref="msgContainer">
      <div v-for="(m, i) in messages" :key="i" class="msg-item" :class="m.role">
        <div v-if="m.role === 'assistant' && m.aiopsPlan" class="aiops-progress">
          <div class="plan-steps">
            <div v-for="(step, si) in m.aiopsPlan" :key="si"
                 :class="['plan-step', { done: m.aiopsResults?.[si], current: m.aiopsCurrent === si }]">
              <span class="step-dot">{{ m.aiopsResults?.[si] ? '&#10003;' : si + 1 }}</span>
              <span class="step-name">{{ step }}</span>
            </div>
          </div>
        </div>
        <div class="msg-content" v-html="m.html" v-if="m.html"></div>
        <div v-if="m.role === 'assistant' && loading && !m.html" class="msg-empty">思考中...</div>
      </div>
    </div>
    <div class="input-area">
      <textarea v-model="input" ref="inputBox" @keydown.enter.exact.prevent="send"
                placeholder="输入消息，Enter 发送..."></textarea>
      <button @click="send" :disabled="loading">发送</button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, watch, onMounted } from 'vue';
import { apiRequest } from '../utils/api';
import { marked } from 'marked';

marked.setOptions({ breaks: true, gfm: true });

const props = defineProps({
  sessions: Array, chatMode: String, currentSessionId: String,
});
const emit = defineEmits(['sessions-changed']);

const messages = ref([]);
const input = ref('');
const loading = ref(false);
const msgContainer = ref(null);
const inputBox = ref(null);

function scrollBottom() {
  nextTick(() => {
    const el = msgContainer.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

function renderMd(text) { return text ? marked.parse(text) : ''; }

function getApiUrl() {
  const map = { chat: '/api/chat', agent: '/api/agent/chat', mcp: '/api/mcp/chat' };
  return (map[props.chatMode] || '/api/chat') + '_stream';
}

function autoName(text) {
  const session = props.sessions?.find(s => s.session_id === props.currentSessionId);
  if (!session || !/^会话 \d+$/.test(session.title)) return;
  const plain = text.replace(/[#*`~>\[\]()!_]/g, '').replace(/\s+/g, ' ').trim();
  session.title = plain.slice(0, 25) || '未命名';
}

async function summarize() {
  const recent = messages.value.slice(-6);
  const content = recent.map(m => `${m.role === 'user' ? '用户' : 'AI'}：${m.html?.replace(/<[^>]*>/g,'').slice(0,300)}`).join('\n');
  if (!content.trim()) return;
  try {
    const r = await apiRequest('/api/title/summarize', { method: 'POST', body: JSON.stringify({ content }) });
    const d = await r.json();
    const session = props.sessions?.find(s => s.session_id === props.currentSessionId);
    if (session && d.title?.length >= 2) {
      session.title = d.title;
      // 回写数据库，避免重新加载会话列表后标题丢失
      apiRequest(`/api/sessions/${encodeURIComponent(props.currentSessionId)}/title`, {
        method: 'PUT',
        body: JSON.stringify({ title: d.title }),
      }).catch(() => {});
      emit('sessions-changed');
    }
  } catch (e) { /* 降级 */ }
}

async function send() {
  const text = input.value.trim();
  if (!text || loading.value) return;
  input.value = '';

  messages.value.push({ role: 'user', html: renderMd(text) });
  autoName(text);
  scrollBottom();
  loading.value = true;

  messages.value.push({ role: 'assistant', html: '' });
  const msg = messages.value[messages.value.length - 1];
  let buffer = '';

  try {
    const resp = await apiRequest(getApiUrl(), {
      method: 'POST',
      body: JSON.stringify({ question: text, session_id: props.currentSessionId }),
    });
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let leftover = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      leftover += dec.decode(value, { stream: true });
      const lines = leftover.split('\n');
      leftover = lines.pop() || '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const evt = JSON.parse(line.slice(6));
          if (evt.type === 'content') { buffer += evt.data; msg.html = renderMd(buffer); scrollBottom(); }
          else if (evt.type === 'done') { msg.html = renderMd(buffer); }
          else if (evt.type === 'error') { msg.html = renderMd(`**出错：** ${evt.data}`); }
        } catch (e) {}
      }
    }
  } catch (e) {
    msg.html = renderMd(`**连接失败：** ${e.message}`);
  } finally {
    loading.value = false;
    scrollBottom();
    summarize();
  }
}

function sendDiagnoseMessage(scope) {
  const text = scope.trim() ? `启动系统诊断，重点关注：${scope}` : '启动系统全面诊断';
  messages.value.push({ role: 'user', html: renderMd(text) });
  scrollBottom();
  loading.value = true;
  runAIOps();
}

async function runAIOps() {
  messages.value.push({ role: 'assistant', html: '', aiopsPlan: [], aiopsResults: {}, aiopsCurrent: -1 });
  const msg = messages.value[messages.value.length - 1];
  let buffer = '';

  try {
    const resp = await apiRequest('/api/aiops', {
      method: 'POST',
      body: JSON.stringify({ session_id: props.currentSessionId }),
    });
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let leftover = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      leftover += dec.decode(value, { stream: true });
      const lines = leftover.split('\n');
      leftover = lines.pop() || '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const evt = JSON.parse(line.slice(6));
          if (evt.type === 'plan') { msg.aiopsPlan = evt.data.steps; msg.html = '<em>正在执行诊断计划…</em>'; scrollBottom(); }
          else if (evt.type === 'step_start') { const i = msg.aiopsPlan.indexOf(evt.data); if (i !== -1) msg.aiopsCurrent = i; }
          else if (evt.type === 'step_result') { const i = msg.aiopsPlan.indexOf(evt.data.step); if (i !== -1) msg.aiopsResults[i] = evt.data.result; }
          else if (evt.type === 'replan') { msg.aiopsPlan = evt.data.new_plan; msg.aiopsResults = {}; msg.aiopsCurrent = -1; msg.html = '<em>计划已调整…</em>'; }
          else if (evt.type === 'report') { buffer = evt.data; msg.html = renderMd(buffer); scrollBottom(); }
          else if (evt.type === 'error') { msg.html = renderMd(`**出错：** ${evt.data}`); }
        } catch (e) {}
      }
    }
  } catch (e) {
    msg.html = renderMd(`**连接失败：** ${e.message}`);
  } finally {
    loading.value = false;
    scrollBottom();
  }
}

function clearMessages() { messages.value = []; }
async function loadMessages(id) {
  clearMessages();
  try {
    const resp = await apiRequest(`/api/sessions/${encodeURIComponent(id)}/messages`);
    const data = await resp.json();
    const list = data?.messages || [];
    messages.value = list.map(m => ({
      role: m.role === 'user' ? 'user' : 'assistant',
      html: renderMd(m.content),
    }));
  } catch (e) {
    /* 加载失败降级为空会话 */
  }
  scrollBottom();
}

onMounted(() => inputBox.value?.focus());

defineExpose({ clearMessages, loadMessages, sendDiagnoseMessage });
</script>

<style scoped>
.chat-container { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.msg-list { flex: 1; overflow-y: auto; padding: 24px; }
.msg-item { margin-bottom: 20px; max-width: 768px; }
.msg-item.user { margin-left: auto; }
.msg-item.user .msg-content { background: #E8E8ED; border-radius: 18px 18px 4px 18px; padding: 12px 18px; }
.msg-item.assistant .msg-content { padding: 4px 0; }
.msg-content :deep(pre) {
  background: #1e1e1e; color: #d4d4d4; padding: 16px; border-radius: 8px; overflow-x: auto;
  font-size: 13px; line-height: 1.5;
}
.msg-content :deep(p) { margin: 4px 0; line-height: 1.6; }
.msg-empty { color: var(--text-secondary); font-style: italic; padding: 8px 0; }

.aiops-progress { margin-bottom: 12px; }
.plan-step { display: flex; align-items: center; gap: 8px; padding: 6px 0; font-size: 13px; color: var(--text-secondary); }
.plan-step.done { color: #16a34a; }
.plan-step.current { color: var(--accent); font-weight: 600; }
.step-dot { width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; background: rgba(0,0,0,0.06); }
.plan-step.done .step-dot { background: #dcfce7; color: #16a34a; }
.plan-step.current .step-dot { background: rgba(37,99,235,0.1); color: var(--accent); }

.input-area { display: flex; gap: 10px; padding: 16px 24px; border-top: 1px solid var(--sidebar-border); background: rgba(255,255,255,0.65); }
.input-area textarea {
  flex: 1; padding: 12px 16px; border: 1px solid var(--sidebar-border); border-radius: 12px;
  font-size: 14px; font-family: inherit; resize: none; outline: none; height: 44px; max-height: 150px;
}
.input-area textarea:focus { border-color: var(--accent); }
.input-area button {
  padding: 0 24px; border: none; border-radius: 12px;
  background: var(--accent); color: #fff; font-size: 14px; cursor: pointer;
}
.input-area button:disabled { opacity: 0.5; cursor: default; }
</style>
