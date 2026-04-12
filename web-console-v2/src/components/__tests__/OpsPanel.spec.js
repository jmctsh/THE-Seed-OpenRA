import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import OpsPanel from '../OpsPanel.vue'

function createBus() {
  const handlers = new Map()
  return {
    on(type, handler) {
      handlers.set(type, handler)
    },
    emit(type, data) {
      const handler = handlers.get(type)
      if (handler) handler({ data })
    },
  }
}

describe('OpsPanel', () => {
  it('only exposes restart control and emits game_restart', async () => {
    const bus = createBus()
    const send = vi.fn()
    const wrapper = mount(OpsPanel, {
      props: {
        connected: true,
        send,
        on: bus.on,
      },
    })

    const buttonTexts = wrapper.findAll('button').map((button) => button.text())
    expect(buttonTexts).toContain('重启游戏')
    expect(buttonTexts).not.toContain('启动游戏')
    expect(buttonTexts).not.toContain('停止游戏')

    await wrapper.get('.btn-restart').trigger('click')
    expect(send).toHaveBeenCalledWith('game_restart', {})
  })

  it('renders stale world details from world_snapshot', async () => {
    const bus = createBus()
    const wrapper = mount(OpsPanel, {
      props: {
        connected: false,
        send: () => {},
        on: bus.on,
      },
    })

    bus.emit('world_snapshot', {
      stale: true,
      consecutive_refresh_failures: 4,
      failure_threshold: 3,
      last_refresh_error: 'actors:COMMAND_EXECUTION_ERROR',
    })
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('⚠ 数据过期 (4/3)')
    expect(wrapper.text()).toContain('连续失败 4 / 3')
    expect(wrapper.text()).toContain('最近错误: actors:COMMAND_EXECUTION_ERROR')
    expect(wrapper.text()).toContain('WS 断开')
  })

  it('renders capability truth blocker from world_snapshot', async () => {
    const bus = createBus()
    const wrapper = mount(OpsPanel, {
      props: {
        connected: true,
        send: () => {},
        on: bus.on,
      },
    })

    bus.emit('world_snapshot', {
      player_faction: 'allied',
      capability_truth_blocker: 'faction_roster_unsupported',
    })
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('能力真值受限')
    expect(wrapper.text()).toContain('demo capability roster 未覆盖 (allied)')
    expect(wrapper.text()).toContain('阵营: allied')
  })
})
