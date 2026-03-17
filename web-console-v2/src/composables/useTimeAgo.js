import { ref, onMounted, onUnmounted } from 'vue'

export function formatTimeAgo(timestamp) {
  if (!timestamp) return ''
  const now = Date.now() / 1000
  const diff = Math.max(0, now - timestamp)
  if (diff < 5) return 'just now'
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

export function useTimeAgo() {
  const tick = ref(0)
  let timer = null
  onMounted(() => { timer = setInterval(() => tick.value++, 1000) })
  onUnmounted(() => clearInterval(timer))
  return { tick, formatTimeAgo }
}
