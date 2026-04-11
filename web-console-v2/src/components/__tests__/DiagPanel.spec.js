import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DiagPanel from '../DiagPanel.vue'

function createBus() {
  const handlers = new Map()
  return {
    on(type, handler) {
      handlers.set(type, handler)
      return () => handlers.delete(type)
    },
    emit(type, data, timestamp = 123) {
      const handler = handlers.get(type)
      if (handler) handler({ data, timestamp })
    },
  }
}

describe('DiagPanel', () => {
  beforeEach(() => {
    window.sessionStorage.clear()
  })

  it('renders structured triage blocker and reservation fields for the selected task', async () => {
    const bus = createBus()
    const send = vi.fn()
    const wrapper = mount(DiagPanel, {
      props: {
        send,
        on: bus.on,
      },
    })

    bus.emit('task_list', {
      tasks: [
        {
          task_id: 't_cap',
          raw_text: '发展科技',
          status: 'running',
          timestamp: 100,
          created_at: 90,
          triage: {
            status_line: '能力处理中：分发请求中 | blocker=缺少前置建筑 (1)',
            state: 'running',
            phase: 'dispatch',
            waiting_reason: 'missing_prerequisite',
            blocking_reason: 'missing_prerequisite',
            reservation_ids: ['res_1', 'res_2'],
            world_stale: true,
          },
        },
      ],
    })
    await wrapper.vm.$nextTick()

    await wrapper.find('#task-trace-select').setValue('t_cap')
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('能力处理中：分发请求中 | blocker=缺少前置建筑 (1)')
    expect(wrapper.text()).toContain('waiting=missing_prerequisite')
    expect(wrapper.text()).toContain('blocker=missing_prerequisite')
    expect(wrapper.text()).toContain('reservations=2')
    expect(wrapper.text()).toContain('world=stale')
  })
})
