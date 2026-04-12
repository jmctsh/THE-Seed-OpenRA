import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useWebSocket } from '../useWebSocket.js'

class FakeWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static CLOSED = 3
  static instances = []

  constructor(url) {
    this.url = url
    this.readyState = FakeWebSocket.CONNECTING
    this.sent = []
    this.closeCalls = 0
    this.onopen = null
    this.onclose = null
    this.onerror = null
    this.onmessage = null
    FakeWebSocket.instances.push(this)
  }

  send(payload) {
    this.sent.push(payload)
  }

  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  close() {
    this.closeCalls += 1
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.()
  }

  emitMessage(payload) {
    this.onmessage?.({ data: JSON.stringify(payload) })
  }
}

function mountComposable(url = 'ws://unit-test/ws') {
  let state
  const Harness = defineComponent({
    setup() {
      state = useWebSocket(url)
      return () => h('div')
    },
  })
  const wrapper = mount(Harness)
  return { wrapper, state }
}

describe('useWebSocket', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.useFakeTimers()
    vi.stubGlobal('WebSocket', FakeWebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('sends sync_request on connect/reconnect and clears buffered messages after reconnect', async () => {
    const { wrapper, state } = mountComposable()

    expect(FakeWebSocket.instances).toHaveLength(1)
    const firstSocket = FakeWebSocket.instances[0]
    firstSocket.open()

    expect(state.connected.value).toBe(true)
    expect(state.reconnecting.value).toBe(false)
    expect(firstSocket.sent).toHaveLength(1)
    expect(JSON.parse(firstSocket.sent[0])).toMatchObject({ type: 'sync_request' })

    firstSocket.emitMessage({ type: 'world_snapshot', data: { tick: 1 } })
    firstSocket.emitMessage({ type: 'task_list', data: { tasks: [] } })
    expect(state.messages.value).toHaveLength(2)

    firstSocket.close()
    expect(state.connected.value).toBe(false)
    expect(state.reconnecting.value).toBe(true)

    await vi.advanceTimersByTimeAsync(3000)
    expect(FakeWebSocket.instances).toHaveLength(2)

    const secondSocket = FakeWebSocket.instances[1]
    secondSocket.open()

    expect(state.connected.value).toBe(true)
    expect(state.reconnecting.value).toBe(false)
    expect(state.messages.value).toEqual([])
    expect(secondSocket.sent).toHaveLength(1)
    expect(JSON.parse(secondSocket.sent[0])).toMatchObject({ type: 'sync_request' })

    wrapper.unmount()
  })

  it('gates send on socket readiness, supports handler unsubscribe, and disconnects on unmount', async () => {
    const { wrapper, state } = mountComposable()
    const socket = FakeWebSocket.instances[0]

    expect(state.send('command_submit', { text: '推进前线' })).toBe(false)

    const handler = vi.fn()
    const wildcard = vi.fn()
    const off = state.on('query_response', handler)
    state.on('*', wildcard)

    socket.open()
    expect(state.send('command_submit', { text: '推进前线' })).toBe(true)
    expect(JSON.parse(socket.sent[1])).toMatchObject({
      type: 'command_submit',
      text: '推进前线',
    })

    socket.emitMessage({ type: 'query_response', data: { answer: '收到' } })
    expect(handler).toHaveBeenCalledTimes(1)
    expect(wildcard).toHaveBeenCalledTimes(1)

    off()
    socket.emitMessage({ type: 'query_response', data: { answer: '再次收到' } })
    expect(handler).toHaveBeenCalledTimes(1)
    expect(wildcard).toHaveBeenCalledTimes(2)

    wrapper.unmount()
    expect(socket.closeCalls).toBe(1)
    expect(state.reconnecting.value).toBe(false)

    await vi.advanceTimersByTimeAsync(3000)
    expect(FakeWebSocket.instances).toHaveLength(1)
  })
})
