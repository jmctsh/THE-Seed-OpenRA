const LABELS_KEY = 'theseed_task_labels_session'
const HIDDEN_KEY = 'theseed_hidden_tasks_session'

function loadJson(key, fallback) {
  try {
    const raw = sessionStorage.getItem(key)
    return raw ? JSON.parse(raw) : fallback
  } catch (_) {
    return fallback
  }
}

function saveJson(key, value) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value))
  } catch (_) {
    // ignore storage failures
  }
}

function loadLabelState() {
  return loadJson(LABELS_KEY, { next: 1, labels: {} })
}

function saveLabelState(state) {
  saveJson(LABELS_KEY, state)
}

export function registerTaskLabel(taskId) {
  if (!taskId) return null
  const state = loadLabelState()
  if (!state.labels[taskId]) {
    state.labels[taskId] = state.next
    state.next += 1
    saveLabelState(state)
  }
  return state.labels[taskId]
}

export function registerTaskLabels(tasks) {
  let changed = false
  const state = loadLabelState()
  for (const task of tasks || []) {
    const taskId = task?.task_id
    if (taskId && !state.labels[taskId]) {
      state.labels[taskId] = state.next
      state.next += 1
      changed = true
    }
  }
  if (changed) saveLabelState(state)
}

export function formatTaskLabel(taskId) {
  const index = registerTaskLabel(taskId)
  if (!index) return '任务'
  return `任务 #${String(index).padStart(3, '0')}`
}

export function replaceTaskIdsWithLabels(text) {
  if (!text) return text
  return text.replace(/\bt_[a-z0-9]+\b/gi, (taskId) => formatTaskLabel(taskId))
}

export function loadHiddenTaskIds() {
  return new Set(loadJson(HIDDEN_KEY, []))
}

export function saveHiddenTaskIds(taskIds) {
  saveJson(HIDDEN_KEY, [...taskIds])
}
