import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import TelemetryView from './TelemetryView'
import i18n from '../../../../i18n/i18n'

// Mock contexts
const mockShowToast = vi.fn()
const mockShowModal = vi.fn()
const mockMessages = { router_status: [] }

vi.mock('../../../../contexts/ToastContext', () => ({
  useToast: () => ({ showToast: mockShowToast }),
}))

vi.mock('../../../../contexts/ModalContext', () => ({
  useModal: () => ({ showModal: mockShowModal }),
}))

vi.mock('../../../../contexts/WebSocketContext', () => ({
  useWebSocket: () => ({ messages: mockMessages }),
}))

// Mock API
vi.mock('../../../../services/api', () => ({
  API_MAVLINK_ROUTER: '/api/mavlink-router',
  fetchWithTimeout: vi.fn(),
}))

const TelemetryViewWithProviders = () => (
  <I18nextProvider i18n={i18n}>
    <TelemetryView />
  </I18nextProvider>
)

describe('TelemetryView Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Module', () => {
    it('exports a valid React component named TelemetryView', () => {
      expect(TelemetryView).toBeDefined()
      expect(TelemetryView.name).toBe('TelemetryView')
      expect(typeof TelemetryView).toBe('function')
    })
  })

  describe('Rendering', () => {
    it('renders the main container', () => {
      render(<TelemetryViewWithProviders />)
      expect(screen.getByText(/MAVLink Telemetry Forwarding/i)).toBeInTheDocument()
    })

    it('renders the output form', () => {
      render(<TelemetryViewWithProviders />)

      // Check form elements exist
      expect(screen.getByLabelText(/type/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/host/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/port/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /create/i })).toBeInTheDocument()
    })

    it('renders preset buttons', () => {
      render(<TelemetryViewWithProviders />)

      expect(screen.getByRole('button', { name: /preset qgc/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /preset.*mp/i })).toBeInTheDocument()
    })

    it('shows outputs section when outputs exist', async () => {
      // Mock outputs data
      const { fetchWithTimeout } = await import('../../../../services/api')
      fetchWithTimeout.mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve([
            {
              id: 'test1',
              type: 'tcp_server',
              host: '0.0.0.0',
              port: 14550,
              running: true,
              clients: 0,
            },
          ]),
      })

      render(<TelemetryViewWithProviders />)

      // Wait for outputs to load
      await waitFor(() => {
        expect(screen.getByText(/configured outputs/i)).toBeInTheDocument()
      })
    })
  })

  describe('Form Interaction', () => {
    it('allows changing output type', () => {
      render(<TelemetryViewWithProviders />)

      const typeSelect = screen.getByLabelText(/type/i)
      fireEvent.change(typeSelect, { target: { value: 'udp' } })

      expect(typeSelect.value).toBe('udp')
    })

    it('allows entering host and port', () => {
      render(<TelemetryViewWithProviders />)

      const portInput = screen.getByLabelText(/port/i)
      fireEvent.change(portInput, { target: { value: '5760' } })

      expect(portInput.value).toBe('5760')
    })

    it('applies QGC preset when clicked', async () => {
      render(<TelemetryViewWithProviders />)

      const qgcButton = screen.getByRole('button', { name: /preset qgc/i })
      fireEvent.click(qgcButton)

      await waitFor(() => {
        const typeSelect = screen.getByLabelText(/type/i)
        const portInput = screen.getByLabelText(/port/i)

        expect(typeSelect.value).toBe('udp')
        expect(portInput.value).toBe('14550')
      })
    })
  })

  describe('Data Loading', () => {
    it('calls presets API on mount', async () => {
      const { fetchWithTimeout } = await import('../../../../services/api')
      fetchWithTimeout.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true, presets: {} }),
      })

      render(<TelemetryViewWithProviders />)

      await waitFor(() => {
        expect(fetchWithTimeout).toHaveBeenCalledWith(
          '/api/mavlink-router/presets',
          expect.any(Object)
        )
      })
    })

    it('calls outputs API on mount', async () => {
      const { fetchWithTimeout } = await import('../../../../services/api')
      fetchWithTimeout.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve([]),
      })

      render(<TelemetryViewWithProviders />)

      await waitFor(() => {
        expect(fetchWithTimeout).toHaveBeenCalledWith(
          '/api/mavlink-router/outputs',
          expect.any(Object)
        )
      })
    })
  })

  describe('Error Handling', () => {
    it('shows toast on API error', async () => {
      const { fetchWithTimeout } = await import('../../../../services/api')
      fetchWithTimeout.mockRejectedValue(new Error('Network error'))

      render(<TelemetryViewWithProviders />)

      await waitFor(() => {
        expect(mockShowToast).toHaveBeenCalledWith(expect.any(String), 'error')
      })
    })

    it('falls back to default presets on API failure', async () => {
      const { fetchWithTimeout } = await import('../../../../services/api')
      fetchWithTimeout.mockRejectedValue(new Error('API error'))

      render(<TelemetryViewWithProviders />)

      // Should still render preset buttons with default presets
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /preset qgc/i })).toBeInTheDocument()
      })
    })
  })
})
