import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import OutputForm from './OutputForm'
import i18n from '../../../../i18n/i18n'

// Mock contexts
const mockShowToast = vi.fn()

vi.mock('../../../../contexts/ToastContext', () => ({
  useToast: () => ({ showToast: mockShowToast }),
}))

// Mock API
vi.mock('../../../../services/api', () => ({
  API_MAVLINK_ROUTER: '/api/mavlink-router',
  fetchWithTimeout: vi.fn(),
}))

const OutputFormWithProviders = (props) => (
  <I18nextProvider i18n={i18n}>
    <OutputForm {...props} />
  </I18nextProvider>
)

describe('OutputForm Component', () => {
  const mockReload = vi.fn()

  const defaultProps = {
    reload: mockReload,
    presets: {
      qgc: { type: 'udp', host: '255.255.255.255', port: 14550 },
      missionplanner: { type: 'tcp_client', host: '127.0.0.1', port: 5760 },
    },
    // editId: null, // optional prop for editing mode
    // editData: null // optional prop for editing mode
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Module', () => {
    it('exports a valid React component named OutputForm', () => {
      expect(OutputForm).toBeDefined()
      expect(OutputForm.name).toBe('OutputForm')
      expect(typeof OutputForm).toBe('function')
    })
  })

  describe('Rendering', () => {
    it('renders form elements in create mode', () => {
      render(<OutputFormWithProviders {...defaultProps} />)

      expect(screen.getByLabelText(/type/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/host/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/port/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /create/i })).toBeInTheDocument()
    })

    it('renders form elements in edit mode', () => {
      const editProps = {
        ...defaultProps,
        editId: 'test-id',
        editData: { type: 'udp', host: '192.168.1.100', port: 5760 },
      }

      render(<OutputFormWithProviders {...editProps} />)

      expect(screen.getByRole('button', { name: /update/i })).toBeInTheDocument()
    })

    it('renders preset buttons', () => {
      render(<OutputFormWithProviders {...defaultProps} />)

      expect(screen.getByRole('button', { name: /preset qgc/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /preset.*mp/i })).toBeInTheDocument()
    })

    it('loads edit data correctly', () => {
      const editProps = {
        ...defaultProps,
        editId: 'test-id',
        editData: { type: 'tcp_server', host: '0.0.0.0', port: 14550 },
      }

      render(<OutputFormWithProviders {...editProps} />)

      expect(screen.getByDisplayValue('tcp_server')).toBeInTheDocument()
      expect(screen.getByDisplayValue('0.0.0.0')).toBeInTheDocument()
      expect(screen.getByDisplayValue('14550')).toBeInTheDocument()
    })
  })

  describe('Form Interaction', () => {
    it('updates form fields when changed', () => {
      render(<OutputFormWithProviders {...defaultProps} />)

      const typeSelect = screen.getByLabelText(/type/i)
      const hostInput = screen.getByLabelText(/host/i)
      const portInput = screen.getByLabelText(/port/i)

      fireEvent.change(typeSelect, { target: { value: 'tcp_client' } })
      fireEvent.change(hostInput, { target: { value: '192.168.1.1' } })
      fireEvent.change(portInput, { target: { value: '5760' } })

      expect(typeSelect.value).toBe('tcp_client')
      expect(hostInput.value).toBe('192.168.1.1')
      expect(portInput.value).toBe('5760')
    })

    it('applies QGC preset when clicked', () => {
      render(<OutputFormWithProviders {...defaultProps} />)

      const qgcButton = screen.getByRole('button', { name: /preset qgc/i })
      fireEvent.click(qgcButton)

      const typeSelect = screen.getByLabelText(/type/i)
      const hostInput = screen.getByLabelText(/host/i)
      const portInput = screen.getByLabelText(/port/i)

      expect(typeSelect.value).toBe('udp')
      expect(hostInput.value).toBe('255.255.255.255')
      expect(portInput.value).toBe('14550')
    })

    it('applies Mission Planner preset when clicked', () => {
      render(<OutputFormWithProviders {...defaultProps} />)

      const mpButton = screen.getByRole('button', { name: /preset.*mp/i })
      fireEvent.click(mpButton)

      const typeSelect = screen.getByLabelText(/type/i)
      const hostInput = screen.getByLabelText(/host/i)
      const portInput = screen.getByLabelText(/port/i)

      expect(typeSelect.value).toBe('tcp_client')
      expect(hostInput.value).toBe('127.0.0.1')
      expect(portInput.value).toBe('5760')
    })
  })

  describe('Form Validation', () => {
    it('validates port range', async () => {
      render(<OutputFormWithProviders {...defaultProps} />)

      const portInput = screen.getByLabelText(/port/i)
      const submitButton = screen.getByRole('button', { name: /create/i })

      fireEvent.change(portInput, { target: { value: '80' } })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(mockShowToast).toHaveBeenCalledWith(
          expect.stringMatching(/port.*1024.*65535/i),
          'error'
        )
      })
    })

    it('validates host IP format', async () => {
      render(<OutputFormWithProviders {...defaultProps} />)

      const hostInput = screen.getByLabelText(/host/i)
      const submitButton = screen.getByRole('button', { name: /create/i })

      fireEvent.change(hostInput, { target: { value: 'invalid-ip' } })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(mockShowToast).toHaveBeenCalledWith(expect.stringMatching(/valid.*ip/i), 'error')
      })
    })

    it('requires all fields', async () => {
      render(<OutputFormWithProviders {...defaultProps} />)

      const submitButton = screen.getByRole('button', { name: /create/i })

      // Clear required fields
      const hostInput = screen.getByLabelText(/host/i)
      fireEvent.change(hostInput, { target: { value: '' } })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(mockShowToast).toHaveBeenCalledWith(expect.stringMatching(/required|fill/i), 'error')
      })
    })
  })

  describe('Form Submission', () => {
    it('submits create request with valid data', async () => {
      const { fetchWithTimeout } = await import('../../../../services/api')
      fetchWithTimeout.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true, message: 'Output created' }),
      })

      render(<OutputFormWithProviders {...defaultProps} />)

      const typeSelect = screen.getByLabelText(/type/i)
      const hostInput = screen.getByLabelText(/host/i)
      const portInput = screen.getByLabelText(/port/i)
      const submitButton = screen.getByRole('button', { name: /create/i })

      fireEvent.change(typeSelect, { target: { value: 'udp' } })
      fireEvent.change(hostInput, { target: { value: '127.0.0.1' } })
      fireEvent.change(portInput, { target: { value: '5760' } })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(fetchWithTimeout).toHaveBeenCalledWith(
          '/api/mavlink-router/outputs',
          expect.objectContaining({
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              type: 'udp',
              host: '127.0.0.1',
              port: 5760,
            }),
          })
        )
      })

      expect(mockReload).toHaveBeenCalled()
    })

    it('submits update request for edit mode', async () => {
      const { fetchWithTimeout } = await import('../../../../services/api')
      fetchWithTimeout.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true, message: 'Output updated' }),
      })

      const editProps = {
        ...defaultProps,
        editId: 'test-id',
        editData: { type: 'udp', host: '192.168.1.100', port: 5760 },
      }

      render(<OutputFormWithProviders {...editProps} />)

      const submitButton = screen.getByRole('button', { name: /update/i })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(fetchWithTimeout).toHaveBeenCalledWith(
          '/api/mavlink-router/outputs/test-id',
          expect.objectContaining({
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
          })
        )
      })
    })

    it('handles API errors gracefully', async () => {
      const { fetchWithTimeout } = await import('../../../../services/api')
      fetchWithTimeout.mockResolvedValue({
        ok: false,
        json: () => Promise.resolve({ error: 'Port already in use' }),
      })

      render(<OutputFormWithProviders {...defaultProps} />)

      const typeSelect = screen.getByLabelText(/type/i)
      const hostInput = screen.getByLabelText(/host/i)
      const portInput = screen.getByLabelText(/port/i)
      const submitButton = screen.getByRole('button', { name: /create/i })

      fireEvent.change(typeSelect, { target: { value: 'udp' } })
      fireEvent.change(hostInput, { target: { value: '127.0.0.1' } })
      fireEvent.change(portInput, { target: { value: '5760' } })
      fireEvent.click(submitButton)

      await waitFor(() => {
        expect(mockShowToast).toHaveBeenCalledWith('Port already in use', 'error')
      })
    })
  })
})
