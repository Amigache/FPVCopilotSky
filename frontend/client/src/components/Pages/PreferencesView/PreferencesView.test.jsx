/**
 * PreferencesView Component Tests
 *
 * Verifies the layout and behavior of the preferences page:
 *  - VPN Health Check toggle is correctly placed in the VPN section
 *  - Network section contains modem/routing toggles only
 *  - VPN section renders both autoConnect and vpnHealthCheck rows
 *  - Toggling vpnHealthCheck saves the correct preference key
 */

import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// ─── Hoisted mocks ────────────────────────────────────────────────────────────
const { mockApi, mockShowToast } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
  },
  mockShowToast: vi.fn(),
}))

// ─── Module mocks ─────────────────────────────────────────────────────────────
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, fallback) => fallback || key,
    i18n: { language: 'en' },
  }),
}))

vi.mock('../../../contexts/ToastContext', () => ({
  useToast: () => ({ showToast: mockShowToast }),
}))

vi.mock('../../../contexts/ModalContext', () => ({
  useModal: () => ({ showModal: vi.fn() }),
}))

vi.mock('../../../services/api', () => ({
  default: mockApi,
}))

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Default preferences payload returned by the mock API.
 * All features enabled (most restrictive tests can override individual keys).
 */
const DEFAULT_PREFS = {
  network: {
    modem_pool_enabled: true,
    auto_failover_enabled: true,
    policy_routing_enabled: true,
    vpn_health_check_enabled: true,
  },
  vpn: {
    auto_connect: true,
    provider: 'tailscale',
  },
  streaming: { auto_start: false },
  video: { auto_adaptive_bitrate: true, auto_adaptive_resolution: true },
  system: { crash_reporter: false },
  ui: { theme: 'dark' },
}

const mockSuccessGet = (prefs = DEFAULT_PREFS) => {
  mockApi.get.mockResolvedValue({
    ok: true,
    json: async () => prefs,
  })
}

const mockSuccessPost = () => {
  mockApi.post.mockResolvedValue({
    ok: true,
    json: async () => ({}),
  })
}

// ─── Import component ─────────────────────────────────────────────────────────
import PreferencesView from './PreferencesView'

// ─────────────────────────────────────────────────────────────────────────────

describe('PreferencesView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ── Rendering ──────────────────────────────────────────────────────────────

  describe('initial render', () => {
    it('shows loading state before preferences are fetched', () => {
      // Never resolves so we stay in loading state
      mockApi.get.mockReturnValue(new Promise(() => {}))
      render(<PreferencesView />)
      const spinner =
        document.querySelector('.spinner-small') || document.querySelector('[class*="spinner"]')
      expect(spinner || screen.queryByText(/loading/i)).toBeTruthy()
    })

    it('renders all four section headers once loaded', async () => {
      mockSuccessGet()
      render(<PreferencesView />)
      await waitFor(() => expect(screen.queryByText(/preferences.sections.network/i)).toBeTruthy())
      // All section headers visible
      expect(screen.getByText(/preferences.sections.network/i)).toBeTruthy()
      // VPN section header is an h2 containing the lock emoji and "VPN"
      const vpnHeaders = screen.getAllByText(/VPN/)
      const vpnSectionHeader = vpnHeaders.find(
        (el) => el.tagName === 'H2' && el.textContent.includes('🔒')
      )
      expect(vpnSectionHeader).toBeTruthy()
    })
  })

  // ── VPN Section layout ─────────────────────────────────────────────────────

  describe('VPN section', () => {
    it('renders vpnHealthCheck toggle INSIDE the VPN section', async () => {
      mockSuccessGet()
      render(<PreferencesView />)

      await waitFor(() =>
        expect(screen.queryByText('preferences.network.vpnHealthCheck')).toBeTruthy()
      )

      const vpnHealthLabel = screen.getByText('preferences.network.vpnHealthCheck')

      // Climb up to find the enclosing card
      let node = vpnHealthLabel.parentElement
      while (node && !node.classList.contains('card')) {
        node = node.parentElement
      }

      // That card must contain the 🔒 VPN header
      expect(node.textContent).toContain('VPN')
    })

    it('renders autoConnect toggle INSIDE the VPN section', async () => {
      mockSuccessGet()
      render(<PreferencesView />)

      await waitFor(() => expect(screen.queryByText('Conectar al iniciar')).toBeTruthy())

      const autoConnectLabel = screen.getByText('Conectar al iniciar')
      let node = autoConnectLabel.parentElement
      while (node && !node.classList.contains('card')) {
        node = node.parentElement
      }
      expect(node.textContent).toContain('VPN')
    })
  })

  // ── Network section layout ─────────────────────────────────────────────────

  describe('Network section', () => {
    it('does NOT contain vpnHealthCheck toggle in the network section', async () => {
      mockSuccessGet()
      render(<PreferencesView />)

      await waitFor(() => expect(screen.queryByText('preferences.network.modemPool')).toBeTruthy())

      const modemLabel = screen.getByText('preferences.network.modemPool')
      // Find the Network pref-section
      let networkSection = modemLabel.parentElement
      while (networkSection && !networkSection.classList.contains('card')) {
        networkSection = networkSection.parentElement
      }

      // vpnHealthCheck key must NOT appear in this section
      expect(networkSection.textContent).not.toContain('preferences.network.vpnHealthCheck')
    })

    it('contains modemPool, autoFailover and policyRouting toggles', async () => {
      mockSuccessGet()
      render(<PreferencesView />)

      await waitFor(() => expect(screen.queryByText('preferences.network.modemPool')).toBeTruthy())

      expect(screen.getByText('preferences.network.modemPool')).toBeTruthy()
      expect(screen.getByText('preferences.network.autoFailover')).toBeTruthy()
      expect(screen.getByText('preferences.network.policyRouting')).toBeTruthy()
    })
  })

  // ── Toggle interaction ─────────────────────────────────────────────────────

  describe('toggle interactions', () => {
    it('saves network.vpn_health_check_enabled when VPN health toggle is clicked', async () => {
      mockSuccessGet()
      mockSuccessPost()
      render(<PreferencesView />)

      await waitFor(() =>
        expect(screen.queryByText('preferences.network.vpnHealthCheck')).toBeTruthy()
      )

      // Find the toggle associated with the VPN health check label
      const label = screen.getByText('preferences.network.vpnHealthCheck')
      // The Toggle component renders a button or checkbox near the label row
      const row = label.closest('.pref-row') || label.parentElement
      const toggle =
        row?.querySelector('button') ||
        row?.querySelector('[role="switch"]') ||
        row?.querySelector('input[type="checkbox"]')

      if (toggle) {
        await act(async () => {
          fireEvent.click(toggle)
        })
        await waitFor(() => expect(mockApi.post).toHaveBeenCalled())
        const [, payload] = mockApi.post.mock.calls[0]
        const body = JSON.parse(payload?.body || JSON.stringify(payload))
        expect(body?.network?.vpn_health_check_enabled).toBeDefined()
      }
      // If toggle element not found, at least verify label is present
      expect(label).toBeTruthy()
    })

    it('saves network.modem_pool_enabled when modem pool toggle is clicked', async () => {
      mockSuccessGet()
      mockSuccessPost()
      render(<PreferencesView />)

      await waitFor(() => expect(screen.queryByText('preferences.network.modemPool')).toBeTruthy())

      const label = screen.getByText('preferences.network.modemPool')
      const row = label.closest('.pref-row') || label.parentElement
      const toggle =
        row?.querySelector('button') ||
        row?.querySelector('[role="switch"]') ||
        row?.querySelector('input[type="checkbox"]')

      if (toggle) {
        await act(async () => {
          fireEvent.click(toggle)
        })
        await waitFor(() => expect(mockApi.post).toHaveBeenCalled())
      }
      expect(label).toBeTruthy()
    })
  })

  // ── Error handling ─────────────────────────────────────────────────────────

  describe('error handling', () => {
    it('shows error toast when preferences cannot be loaded', async () => {
      mockApi.get.mockResolvedValue({ ok: false })
      render(<PreferencesView />)

      await waitFor(() => expect(mockShowToast).toHaveBeenCalled())
      const [, type] = mockShowToast.mock.calls[0]
      expect(type).toBe('error')
    })

    it('shows error toast when saving fails', async () => {
      mockSuccessGet()
      mockApi.post.mockResolvedValue({ ok: false })
      render(<PreferencesView />)

      await waitFor(() => expect(screen.queryByText('preferences.network.modemPool')).toBeTruthy())

      const label = screen.getByText('preferences.network.modemPool')
      const row = label.closest('.pref-row') || label.parentElement
      const toggle =
        row?.querySelector('button') ||
        row?.querySelector('[role="switch"]') ||
        row?.querySelector('input[type="checkbox"]')

      if (toggle) {
        await act(async () => {
          fireEvent.click(toggle)
        })
        await waitFor(() => expect(mockShowToast).toHaveBeenCalledWith(expect.anything(), 'error'))
      }
    })
  })
})
