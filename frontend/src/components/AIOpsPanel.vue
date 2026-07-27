<template>
  <div class="modal-backdrop" @click.self="$emit('cancel')">
    <div class="modal-card">
      <h3>AIOps 智能诊断</h3>
      <p>输入诊断范围（可选，留空则全面诊断）</p>
      <textarea v-model="scope" ref="diagInput" placeholder="例如：检查 CPU 和内存使用情况..."
                @keydown.enter.exact.prevent="confirm"></textarea>
      <div class="modal-actions">
        <button class="btn-cancel" @click="$emit('cancel')">取消</button>
        <button class="btn-confirm" @click="confirm">开始诊断</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
const emit = defineEmits(['confirm', 'cancel']);
const scope = ref('');
const diagInput = ref(null);

function confirm() { emit('confirm', scope.value); }
onMounted(() => diagInput.value?.focus());
</script>

<style scoped>
.modal-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,0.3); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.modal-card {
  background: #fff; border-radius: 16px; padding: 32px; width: 480px; max-width: 90vw;
  box-shadow: 0 20px 60px rgba(0,0,0,0.15);
}
.modal-card h3 { font-size: 20px; margin-bottom: 8px; }
.modal-card p { color: var(--text-secondary); font-size: 14px; margin-bottom: 16px; }
.modal-card textarea {
  width: 100%; padding: 12px 16px; border: 1px solid var(--sidebar-border); border-radius: 10px;
  font-size: 14px; font-family: inherit; resize: none; outline: none; height: 80px;
}
.modal-card textarea:focus { border-color: var(--accent); }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
.btn-cancel { padding: 8px 20px; border: 1px solid var(--sidebar-border); border-radius: 8px; background: #fff; cursor: pointer; font-size: 14px; }
.btn-confirm { padding: 8px 20px; border: none; border-radius: 8px; background: var(--accent); color: #fff; cursor: pointer; font-size: 14px; }
</style>
