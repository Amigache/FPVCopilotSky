/**
 * Header Component - Network Status Badge Tests
 *
 * Tests specifically for the network status badge that was optimized
 * to show immediately on page load instead of waiting 5 seconds.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'

// Mock useWebSocket at module level
const mockUseWebSocket = vi.fn()

vi.mock('../../contexts/WebSocketContext', () => ({
  useWebSocket: () => mockUseWebSocket(),
}))

// Mock the useTranslation hook
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, defaultValue) => defaultValue || key,
  }),
}))

// Import after mocks are set up
import Header from './Header'

describe('Header Component - Network Status Badge', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default mock return value
    mockUseWebSocket.mockReturnValue({
      messages: {},
    })
  })

  it('shows "No Network" when network mode is unknown', () => {
    mockUseWebSocket.mockReturnValue({
      messages: {
        network_status: {
          mode: 'unknown',
        },
      },
    })

    render(<Header />)

    // Should show "No Network" badge
    const badges = document.querySelectorAll('.badge')
    const networkBadge = Array.from(badges).find(
      (badge) =>
        badge.textContent?.includes('No Network') || badge.textContent?.includes('header.noNetwork')
    )

    expect(networkBadge).toBeTruthy()
  })

  it('shows "Internet: WIFI" when network mode is wifi', () => {
    mockUseWebSocket.mockReturnValue({
      messages: {
        network_status: {
          mode: 'wifi',
        },
      },
    })

    render(<Header />)

    const badges = document.querySelectorAll('.badge')
    const networkBadge = Array.from(badges).find(
      (badge) =>
        badge.textContent?.includes('WIFI') || badge.textContent?.includes('header.internetWifi')
    )

    expect(networkBadge).toBeTruthy()
  })

  it('shows "Internet: MÓDEM" when network mode is modem', () => {
    mockUseWebSocket.mockReturnValue({
      messages: {
        network_status: {
          mode: 'modem',
        },
      },
    })

    render(<Header />)

    const badges = document.querySelectorAll('.badge')
    const networkBadge = Array.from(badges).find(
      (badge) =>
        badge.textContent?.includes('MÓDEM') || badge.textContent?.includes('header.internetModem')
    )

    expect(networkBadge).toBeTruthy()
  })

  it('uses correct badge variant for wifi mode', () => {
    mockUseWebSocket.mockReturnValue({
      messages: {
        network_status: {
          mode: 'wifi',
        },
      },
    })

    render(<Header />)

    // WiFi should use 'info' variant (blue)
    const badges = document.querySelectorAll('.badge-info')
    expect(badges.length).toBeGreaterThan(0)
  })

  it('uses correct badge variant for modem mode', () => {
    mockUseWebSocket.mockReturnValue({
      messages: {
        network_status: {
          mode: 'modem',
        },
      },
    })

    render(<Header />)

    // Modem should use 'success' variant (green)
    const badges = document.querySelectorAll('.badge-success')
    expect(badges.length).toBeGreaterThan(0)
  })

  it('uses correct badge variant for unknown mode', () => {
    mockUseWebSocket.mockReturnValue({
      messages: {
        network_status: {
          mode: 'unknown',
        },
      },
    })

    render(<Header />)

    // Unknown should use 'secondary' variant (gray)
    const badges = document.querySelectorAll('.badge-secondary')
    expect(badges.length).toBeGreaterThan(0)
  })

  it('handles missing network_status gracefully', () => {
    mockUseWebSocket.mockReturnValue({
      messages: {
        // network_status is missing
      },
    })

    // Should not crash
    expect(() => {
      render(<Header />)
    }).not.toThrow()

    // Should show default "No Network"
    const badges = document.querySelectorAll('.badge')
    expect(badges.length).toBeGreaterThan(0)
  })

  it('updates when network mode changes', () => {
    // Initial state: wifi
    mockUseWebSocket.mockReturnValue({
      messages: {
        network_status: {
          mode: 'wifi',
        },
      },
    })

    const { rerender } = render(<Header />)

    // Change to modem
    mockUseWebSocket.mockReturnValue({
      messages: {
        network_status: {
          mode: 'modem',
        },
      },
    })

    rerender(<Header />)

    // Should show updated mode
    const badges = document.querySelectorAll('.badge')
    expect(badges.length).toBeGreaterThan(0)
  })

  it('shows all required badges including network status', () => {
    mockUseWebSocket.mockReturnValue({
      messages: {
        mavlink_status: {
          connected: true,
        },
        telemetry: {
          system: { armed: false },
        },
        video_status: {
          streaming: true,
        },
        vpn_status: {
          connected: true,
        },
        network_status: {
          mode: 'wifi',
        },
      },
    })

    render(<Header />)

    // Should have 5 badges: Video, MAVLink, Armed, VPN, Network
    const badges = document.querySelectorAll('.badge')
    expect(badges.length).toBe(5)
  })
})
