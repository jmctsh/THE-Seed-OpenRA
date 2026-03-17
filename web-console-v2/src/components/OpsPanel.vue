<template>
  <div class="ops-panel">
    <h3>Operations</h3>
    <div class="vnc-container">
      <iframe :src="vncUrl" class="vnc-frame" allowfullscreen></iframe>
    </div>
    <div class="controls">
      <button @click="$emit('mode-switch', 'user')">用户模式</button>
      <button @click="$emit('mode-switch', 'debug')">调试模式</button>
    </div>
    <div class="connection-status">
      <span :class="connected ? 'online' : 'offline'">
        {{ connected ? '● 已连接' : '○ 断开' }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, defineProps, defineEmits } from 'vue'

defineProps({ connected: Boolean })
defineEmits(['mode-switch'])

const vncUrl = ref('about:blank')
</script>

<style scoped>
.ops-panel { padding: 12px; display: flex; flex-direction: column; height: 100%; }
.ops-panel h3 { margin: 0 0 8px; font-size: 14px; color: #666; }
.vnc-container { flex: 1; min-height: 200px; }
.vnc-frame { width: 100%; height: 100%; border: 1px solid #ddd; border-radius: 4px; }
.controls { display: flex; gap: 8px; margin-top: 8px; }
.controls button { padding: 6px 12px; border: 1px solid #ccc; border-radius: 4px; background: #f5f5f5; cursor: pointer; font-size: 12px; }
.controls button:hover { background: #e0e0e0; }
.connection-status { margin-top: 8px; font-size: 12px; }
.online { color: #4caf50; }
.offline { color: #f44336; }
</style>
