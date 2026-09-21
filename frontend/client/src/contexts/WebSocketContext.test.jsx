import { describe, it, expect, vi } from 'vitest'
import { createMessageStore } from './WebSocketContext'

describe('createMessageStore', () => {
  it('returns the latest payload per type', () => {
    const store = createMessageStore()
    expect(store.get('telemetry')).toBeUndefined()
    store.set('telemetry', { system: { armed: true } })
    expect(store.get('telemetry')).toEqual({ system: { armed: true } })
  })

  it('notifies only subscribers of the changed type', () => {
    const store = createMessageStore()
    const onTelemetry = vi.fn()
    const onVideo = vi.fn()
    store.subscribe('telemetry', onTelemetry)
    store.subscribe('video_status', onVideo)

    store.set('telemetry', { armed: true })

    expect(onTelemetry).toHaveBeenCalledTimes(1)
    expect(onVideo).not.toHaveBeenCalled()
  })

  it('does not notify when the same reference is set again', () => {
    const store = createMessageStore()
    const listener = vi.fn()
    store.subscribe('status', listener)

    const payload = { connected: true }
    store.set('status', payload)
    store.set('status', payload)

    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('stops notifying after unsubscribe and cleans up', () => {
    const store = createMessageStore()
    const listener = vi.fn()
    const unsubscribe = store.subscribe('modem_status', listener)

    unsubscribe()
    store.set('modem_status', { ok: true })

    expect(listener).not.toHaveBeenCalled()
  })
})
