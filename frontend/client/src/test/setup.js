/**
 * Vitest test setup
 *
 * Configuration and global setup for all tests
 */

import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom'

// Cleanup after each test
afterEach(() => {
  cleanup()
})

// Mock RTCPeerConnection for WebRTC tests
global.RTCPeerConnection = vi.fn(() => ({
  addTransceiver: vi.fn(),
  close: vi.fn(),
  createOffer: vi.fn(() => Promise.resolve({ sdp: '', type: 'offer' })),
  setLocalDescription: vi.fn(() => Promise.resolve()),
  setRemoteDescription: vi.fn(() => Promise.resolve()),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  getStats: vi.fn(() =>
    Promise.resolve({
      forEach: () => {},
    })
  ),
  addIceCandidate: vi.fn(() => Promise.resolve()),
  ontrack: null,
  oniceconnectionstatechange: null,
  onicecandidate: null,
  iceConnectionState: 'disconnected',
}))

// Mock RTCSessionDescription for WebRTC tests
global.RTCSessionDescription = function (data) {
  return data
}

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {}, // deprecated
    removeListener: () => {}, // deprecated
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => {},
  }),
})

// Mock IntersectionObserver
global.IntersectionObserver = class IntersectionObserver {
  constructor() {}
  disconnect() {}
  observe() {}
  takeRecords() {
    return []
  }
  unobserve() {}
}
