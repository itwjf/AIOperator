<template>
  <div class="mode-bar">
    <div class="mode-tabs">
      <button v-for="(label, key) in modes" :key="key"
              :class="{ active: modelValue === key }"
              @click="switchMode(key)">
        {{ label }}
      </button>
      <div class="mode-indicator" :style="indicatorStyle"></div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({ modelValue: { type: String, default: 'chat' } });
const emit = defineEmits(['update:modelValue', 'diagnose']);

const modes = { chat: 'RAG Agent', agent: '手动 Agent', aiops: 'AIOps 诊断', mcp: 'MCP Agent' };
const keys = Object.keys(modes);

const modeIndex = computed(() => keys.indexOf(props.modelValue));
const indicatorStyle = computed(() => ({
  transform: `translateX(${modeIndex.value * 100}%)`,
  width: `${100 / keys.length}%`,
}));

function switchMode(key) {
  if (key === 'aiops') {
    emit('diagnose');
    return;
  }
  emit('update:modelValue', key);
}
</script>

<style scoped>
.mode-bar { display: flex; align-items: center; }
.mode-tabs {
  position: relative; display: flex;
  background: rgba(0,0,0,0.04); border-radius: 10px; padding: 3px;
}
.mode-tabs button {
  position: relative; z-index: 1; padding: 6px 16px;
  border: none; background: none; font-size: 13px; cursor: pointer;
  color: var(--text-secondary); white-space: nowrap;
  transition: color 0.2s; border-radius: 8px;
}
.mode-tabs button.active { color: var(--text); }
.mode-indicator {
  position: absolute; top: 3px; left: 3px; bottom: 3px;
  background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  transition: transform 0.3s cubic-bezier(0.34,1.56,0.64,1);
}
</style>
