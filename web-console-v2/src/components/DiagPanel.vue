<template>
  <div class="diag-panel">
    <h3>Diagnostics</h3>
    <div class="log-filter">
      <button
        v-for="lvl in ['ALL', 'INFO', 'WARN', 'ERROR']"
        :key="lvl"
        :class="['filter-btn', { active: filterLevel === lvl }]"
        @click="filterLevel = lvl"
      >{{ lvl }}</button>
    </div>
    <div class="log-filter">
      <button
        v-for="component in COMPONENT_FILTERS"
        :key="component"
        :class="['filter-btn', { active: filterComponent === component }]"
        @click="filterComponent = component"
      >{{ component }}</button>
    </div>
    <div class="log-stream" ref="logEl">
      <div v-for="(entry, i) in filteredLogs" :key="i" :class="['log-entry', entry.level?.toLowerCase()]">
        <span class="log-time">{{ formatTime(entry.timestamp) }}</span>
        <span class="log-component">[{{ entry.component || 'log' }}]</span>
        <span v-if="entry.tag && entry.tag !== entry.component" class="log-tag">[{{ entry.tag }}]</span>
        <span class="log-msg">{{ entry.message }}</span>
      </div>
      <div v-if="!filteredLogs.length" class="empty">等待日志...</div>
    </div>

    <h3>Benchmark</h3>
    <div class="benchmark-summary">
      <div v-for="entry in displayedBenchmarks" :key="entry.tag" class="bench-row">
        <span class="bench-tag">{{ entry.tag }}</span>
        <span class="bench-count">{{ entry.stats.count }}次</span>
        <span class="bench-avg">avg {{ entry.stats.avg.toFixed(1) }}ms</span>
        <span class="bench-max">max {{ entry.stats.max.toFixed(1) }}ms</span>
      </div>
      <div v-if="benchmarkOverflowCount > 0" class="bench-note">
        仅显示 top {{ BENCHMARK_LIMIT }} tags，已隐藏 {{ benchmarkOverflowCount }} 项
      </div>
      <div v-if="!displayedBenchmarks.length" class="empty">无数据</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, reactive, defineProps } from 'vue'

const props = defineProps({ on: Function })

const BENCHMARK_LIMIT = 20
const COMPONENT_FILTERS = ['ALL', 'adjutant', 'task_agent', 'kernel', 'expert', 'world_model', 'game_loop']
const LEVEL_ORDER = { DEBUG: 0, INFO: 1, WARN: 2, WARNING: 2, ERROR: 3 }

const logEntries = ref([])
const logEl = ref(null)
const benchmarkStats = reactive({})
const filterLevel = ref('ALL')
const filterComponent = ref('ALL')

const filteredLogs = computed(() => {
  const minLevel = filterLevel.value === 'ALL' ? 0 : (LEVEL_ORDER[filterLevel.value] || 0)
  return logEntries.value.filter((entry) => {
    const entryLevel = LEVEL_ORDER[(entry.level || '').toUpperCase()] || 0
    if (entryLevel < minLevel) return false
    if (filterComponent.value === 'ALL') return true
    return entry.component === filterComponent.value
  })
})

const displayedBenchmarks = computed(() =>
  Object.entries(benchmarkStats)
    .sort(([, left], [, right]) => {
      if (right.count !== left.count) return right.count - left.count
      return right.max - left.max
    })
    .slice(0, BENCHMARK_LIMIT)
    .map(([tag, stats]) => ({ tag, stats }))
)

const benchmarkOverflowCount = computed(() =>
  Math.max(Object.keys(benchmarkStats).length - BENCHMARK_LIMIT, 0)
)

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString()
}

function addLog(entry) {
  logEntries.value.push(entry)
  if (logEntries.value.length > 500) logEntries.value.splice(0, 100)
  nextTick(() => {
    if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
  })
}

function updateBenchmark(records) {
  if (!Array.isArray(records)) return
  const byTag = {}
  for (const record of records) {
    if (!record?.tag) continue
    if (!byTag[record.tag]) byTag[record.tag] = { count: 0, total: 0, max: 0 }
    byTag[record.tag].count += 1
    byTag[record.tag].total += record.duration_ms || 0
    byTag[record.tag].max = Math.max(byTag[record.tag].max, record.duration_ms || 0)
  }
  for (const [tag, stats] of Object.entries(byTag)) {
    benchmarkStats[tag] = {
      count: stats.count,
      avg: stats.total / stats.count,
      max: stats.max,
    }
  }
}

if (props.on) {
  props.on('log_entry', (msg) => {
    const entry = msg.data || msg
    addLog({
      component: entry.component || entry.tag || 'log',
      level: entry.level || 'INFO',
      tag: entry.event || entry.tag || entry.component || 'log',
      message: entry.message || JSON.stringify(entry),
      timestamp: entry.timestamp || msg.timestamp,
    })
  })
  props.on('world_snapshot', (msg) => {
    if (msg.data?.benchmark) updateBenchmark(msg.data.benchmark)
  })
  props.on('benchmark', (msg) => {
    if (msg.data?.records) updateBenchmark(msg.data.records)
  })
}
</script>

<style scoped>
.diag-panel { padding: 12px; display: flex; flex-direction: column; height: 100%; }
.diag-panel h3 { margin: 8px 0; font-size: 14px; color: #666; }
.log-filter { display: flex; gap: 4px; margin-bottom: 6px; flex-wrap: wrap; }
.filter-btn { padding: 2px 8px; border: 1px solid #ccc; border-radius: 3px; background: #f5f5f5; cursor: pointer; font-size: 11px; }
.filter-btn.active { background: #1976d2; color: white; border-color: #1976d2; }
.log-stream { flex: 1; overflow-y: auto; font-family: monospace; font-size: 12px; background: #1e1e1e; color: #d4d4d4; padding: 8px; border-radius: 4px; min-height: 150px; }
.log-entry { margin-bottom: 2px; }
.log-entry.error { color: #f44336; }
.log-entry.warn, .log-entry.warning { color: #ff9800; }
.log-time { color: #888; margin-right: 6px; }
.log-component { color: #81c784; margin-right: 6px; }
.log-tag { color: #4fc3f7; margin-right: 6px; }
.empty { color: #999; font-size: 13px; }
.benchmark-summary { font-size: 12px; }
.bench-row { display: flex; gap: 12px; padding: 4px 0; border-bottom: 1px solid #f0f0f0; }
.bench-tag { font-weight: bold; min-width: 100px; }
.bench-count { color: #666; }
.bench-avg { color: #2196f3; }
.bench-max { color: #f44336; }
.bench-note { margin-top: 6px; font-size: 11px; color: #999; }
</style>
