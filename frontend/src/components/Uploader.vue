<template>
  <div class="upload-area">
    <label class="upload-btn">
      &#8593; 上传文档
      <input type="file" accept=".md,.txt" @change="handleUpload" hidden>
    </label>
    <span v-if="uploadMsg" class="upload-msg">{{ uploadMsg }}</span>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { apiRequest } from '../utils/api';

const uploadMsg = ref('');

async function handleUpload(e) {
  const file = e.target.files?.[0];
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  try {
    const resp = await apiRequest('/api/upload', { method: 'POST', body: form });
    const data = await resp.json();
    uploadMsg.value = `${data.filename} — ${data.chunks} 个分片已入库`;
  } catch (err) {
    uploadMsg.value = `上传失败: ${err.message}`;
  }
  e.target.value = '';
}
</script>

<style scoped>
.upload-area { display: flex; align-items: center; gap: 10px; }
.upload-btn {
  padding: 6px 14px; border: 1px dashed var(--sidebar-border); border-radius: 8px;
  font-size: 13px; cursor: pointer; color: var(--text-secondary);
  transition: border-color 0.2s;
}
.upload-btn:hover { border-color: var(--accent); color: var(--accent); }
.upload-msg { font-size: 12px; color: var(--text-secondary); }
</style>
