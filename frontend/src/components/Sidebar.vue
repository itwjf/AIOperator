<template>
  <aside class="sidebar" :class="{ collapsed }">
    <div class="sidebar-header">
      <button class="btn-new" @click="$emit('new')">+ 新建会话</button>
      <button class="btn-toggle" @click="$emit('toggle')">&#9664;</button>
    </div>
    <ul class="session-list">
      <li v-for="s in sessions" :key="s.session_id"
          :class="{ active: s.session_id === currentSessionId }"
          @click="$emit('switch', s.session_id)">
        <span class="session-name">{{ s.title || '未命名会话' }}</span>
        <button class="btn-delete" @click.stop="$emit('delete', s.session_id)"
                :disabled="sessions.length <= 1">&times;</button>
      </li>
    </ul>
    <div class="sidebar-footer">
      <Uploader />
    </div>
  </aside>
</template>

<script setup>
import Uploader from './Uploader.vue';
defineProps({
  sessions: { type: Array, default: () => [] },
  currentSessionId: { type: String, default: 'default' },
  collapsed: { type: Boolean, default: false },
});
defineEmits(['new', 'switch', 'delete', 'toggle']);
</script>

<style scoped>
.sidebar {
  width: var(--sidebar-width); height: 100vh;
  background: var(--sidebar-bg); backdrop-filter: blur(20px);
  border-right: 1px solid var(--sidebar-border);
  display: flex; flex-direction: column; flex-shrink: 0;
  transition: margin-left var(--transition);
}
.sidebar.collapsed { margin-left: calc(-1 * var(--sidebar-width)); }

.sidebar-header {
  display: flex; align-items: center; gap: 8px; padding: 16px;
  border-bottom: 1px solid var(--sidebar-border);
}
.btn-new {
  flex: 1; padding: 8px 16px; border-radius: 8px;
  background: var(--accent); color: #fff; border: none; font-size: 13px; cursor: pointer;
}
.btn-toggle {
  width: 28px; height: 28px; border: none; background: none; cursor: pointer;
  font-size: 12px; color: var(--text-secondary); border-radius: 6px;
}
.btn-toggle:hover { background: rgba(0,0,0,0.04); }
.session-list { flex: 1; overflow-y: auto; list-style: none; padding: 8px; }
.session-list li {
  padding: 10px 14px; border-radius: 8px; cursor: pointer;
  display: flex; align-items: center; gap: 8px; font-size: 14px;
  color: var(--sidebar-text); transition: background 0.15s;
}
.session-list li:hover { background: rgba(0,0,0,0.04); }
.session-list li.active { background: rgba(37,99,235,0.08); color: var(--accent); }
.session-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.btn-delete {
  opacity: 0; border: none; background: none; cursor: pointer;
  font-size: 16px; color: var(--text-secondary); padding: 0 4px;
}
.session-list li:hover .btn-delete { opacity: 1; }
.btn-delete:disabled { display: none; }
.sidebar-footer { padding: 12px 16px; border-top: 1px solid var(--sidebar-border); }
</style>
