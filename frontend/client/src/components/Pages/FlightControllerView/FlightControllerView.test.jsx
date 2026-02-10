import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Hoisted mocks
const { mockFetchWithTimeout, mockShowToast, mockShowModal, mockMessages } = vi.hoisted(() => ({
  mockFetchWithTimeout: vi.fn(),
  mockShowToast: vi.fn(),
  mockShowModal: vi.fn(),
  mockMessages: {},
}))

// Mock dependencies
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en' },
  }),
}))

vi.mock('../../../contexts/ToastContext', () => ({
  useToast: () => ({ showToast: mockShowToast }),
}))

vi.mock('../../../contexts/WebSocketContext', () => ({
  useWebSocket: () => ({ messages: mockMessages, isConnected: true }),
}))

vi.mock('../../../contexts/ModalContext', () => ({
  useModal: () => ({ showModal: mockShowModal }),
}))

vi.mock('../../../services/api', () => ({
  API_MAVLINK: '/api/mavlink',
  API_SYSTEM: '/api/system',
  fetchWithTimeout: (...args) => mockFetchWithTimeout(...args),
}))

vi.mock('../../Toggle/Toggle', () => ({
  default: ({ checked, onChange, disabled, label }) => (
    <label data-testid="toggle">
      <input
        type="checkbox"
        data-testid="auto-connect-toggle"
        checked={checked}
        onChange={onChange}
        disabled={disabled}
      />
      {label}
    </label>
  ),
}))

import FlightControllerView from './FlightControllerView'

// --- Test data ---
const portsResponse = {
  ports: [
    { path: '/dev/ttyUSB0', name: 'USB Serial' },
    { path: '/dev/ttyACM0', name: 'ACM Serial' },
  ],
}

const emptyPortsResponse = { ports: [] }

const preferencesResponse = {
  success: true,
  preferences: {
    auto_connect: false,
    port: '/dev/ttyACM0',
    baudrate: 57600,
  },
}

const preferencesDefaultResponse = {
  success: true,
  preferences: {
    auto_connect: false,
    port: '',
    baudrate: 115200,
  },
}

const connectSuccessResponse = {
  success: true,
  message: 'Connected',
}

const disconnectSuccessResponse = {
  success: true,
  message: 'Disconnected',
}

const batchGetResponse = {
  parameters: {
    RC_PROTOCOLS: 0,
    FS_GCS_ENABL: 1,
    SR0_EXTRA1: 4,
    SR0_POSITION: 2,
    SR0_EXTRA3: 2,
    SR0_EXT_STAT: 2,
    SR0_RAW_CTRL: 1,
    SR0_RC_CHAN: 1,
  },
  errors: [],
}

const batchSetResponse = {
  success: true,
  results: {
    RC_PROTOCOLS: { success: true, value: 256 },
  },
}

// --- Helpers ---
function jsonResponse(data, ok = true) {
  return {
    ok,
    json: () => Promise.resolve(data),
  }
}

function setupDefaultMocks(prefsOverride = preferencesDefaultResponse) {
  mockFetchWithTimeout.mockImplementation((url) => {
    if (url.includes('/api/system/ports')) {
      return Promise.resolve(jsonResponse(portsResponse))
    }
    if (url.includes('/api/mavlink/preferences')) {
      return Promise.resolve(jsonResponse(prefsOverride))
    }
    if (url.includes('/api/mavlink/params/batch/get')) {
      return Promise.resolve(jsonResponse(batchGetResponse))
    }
    if (url.includes('/api/mavlink/params/batch/set')) {
      return Promise.resolve(jsonResponse(batchSetResponse))
    }
    if (url.includes('/api/mavlink/connect')) {
      return Promise.resolve(jsonResponse(connectSuccessResponse))
    }
    if (url.includes('/api/mavlink/disconnect')) {
      return Promise.resolve(jsonResponse(disconnectSuccessResponse))
    }
    return Promise.resolve(jsonResponse({}, false))
  })
}

async function renderView() {
  let result
  await act(async () => {
    result = render(<FlightControllerView />)
  })
  return result
}

// --- Tests ---
describe('FlightControllerView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Reset messages
    Object.keys(mockMessages).forEach((key) => delete mockMessages[key])
  })

  describe('Module exports', () => {
    it('exports FlightControllerView as default', () => {
      expect(FlightControllerView).toBeDefined()
      expect(typeof FlightControllerView).toBe('function')
    })
  })

  describe('Loading state', () => {
    it('shows loading ports initially', async () => {
      // Make ports request hang
      mockFetchWithTimeout.mockImplementation((url) => {
        if (url.includes('/api/system/ports')) {
          return new Promise(() => {}) // never resolves
        }
        if (url.includes('/api/mavlink/preferences')) {
          return Promise.resolve(jsonResponse(preferencesDefaultResponse))
        }
        return Promise.resolve(jsonResponse({}))
      })

      await act(async () => {
        render(<FlightControllerView />)
      })

      expect(screen.getByText('views.flightController.loadingPorts')).toBeInTheDocument()
    })
  })

  describe('Port list', () => {
    it('renders ports from backend', async () => {
      setupDefaultMocks()
      await renderView()

      await waitFor(() => {
        expect(screen.getByText('/dev/ttyUSB0 (USB Serial)')).toBeInTheDocument()
        expect(screen.getByText('/dev/ttyACM0 (ACM Serial)')).toBeInTheDocument()
      })
    })

    it('shows no ports message when backend returns empty', async () => {
      mockFetchWithTimeout.mockImplementation((url) => {
        if (url.includes('/api/system/ports')) {
          return Promise.resolve(jsonResponse(emptyPortsResponse))
        }
        if (url.includes('/api/mavlink/preferences')) {
          return Promise.resolve(jsonResponse(preferencesDefaultResponse))
        }
        return Promise.resolve(jsonResponse({}))
      })

      await renderView()

      await waitFor(() => {
        expect(screen.getByText('views.flightController.noPortsAvailable')).toBeInTheDocument()
      })
    })

    it('shows no ports on fetch error', async () => {
      mockFetchWithTimeout.mockImplementation((url) => {
        if (url.includes('/api/system/ports')) {
          return Promise.reject(new Error('Network error'))
        }
        if (url.includes('/api/mavlink/preferences')) {
          return Promise.resolve(jsonResponse(preferencesDefaultResponse))
        }
        return Promise.resolve(jsonResponse({}))
      })

      await renderView()

      await waitFor(() => {
        expect(screen.getByText('views.flightController.noPortsAvailable')).toBeInTheDocument()
      })
    })

    it('does not show hardcoded fallback ports', async () => {
      mockFetchWithTimeout.mockImplementation((url) => {
        if (url.includes('/api/system/ports')) {
          return Promise.resolve(jsonResponse(emptyPortsResponse))
        }
        if (url.includes('/api/mavlink/preferences')) {
          return Promise.resolve(jsonResponse(preferencesDefaultResponse))
        }
        return Promise.resolve(jsonResponse({}))
      })

      await renderView()

      await waitFor(() => {
        expect(screen.queryByText(/ttyAML0/)).not.toBeInTheDocument()
      })
    })
  })

  describe('Preferences restore', () => {
    it('restores saved port and baudrate from preferences', async () => {
      setupDefaultMocks(preferencesResponse)
      await renderView()

      await waitFor(() => {
        // The port select should have the saved port selected
        const portSelect = screen.getAllByRole('combobox')[0]
        expect(portSelect.value).toBe('/dev/ttyACM0')

        // The baudrate select should have the saved baudrate
        const baudrateSelect = screen.getAllByRole('combobox')[1]
        expect(baudrateSelect.value).toBe('57600')
      })
    })

    it('keeps defaults when preferences have no saved port', async () => {
      setupDefaultMocks(preferencesDefaultResponse)
      await renderView()

      await waitFor(() => {
        const baudrateSelect = screen.getAllByRole('combobox')[1]
        expect(baudrateSelect.value).toBe('115200')
      })
    })
  })

  describe('Connect flow', () => {
    it('calls connect API with selected port and baudrate', async () => {
      setupDefaultMocks(preferencesResponse)
      await renderView()

      // Wait for port to be restored from preferences
      await waitFor(() => {
        const portSelect = screen.getAllByRole('combobox')[0]
        expect(portSelect.value).toBe('/dev/ttyACM0')
      })

      const connectBtn = screen.getByRole('button', { name: /views\.flightController\.connect/ })
      await act(async () => {
        fireEvent.click(connectBtn)
      })

      await waitFor(() => {
        const connectCall = mockFetchWithTimeout.mock.calls.find((c) =>
          c[0].includes('/api/mavlink/connect')
        )
        expect(connectCall).toBeDefined()
        const body = JSON.parse(connectCall[1].body)
        expect(body.port).toBe('/dev/ttyACM0')
        expect(body.baudrate).toBe(57600)
      })
    })

    it('shows success toast on successful connect', async () => {
      setupDefaultMocks(preferencesResponse)
      await renderView()

      await waitFor(() => {
        const portSelect = screen.getAllByRole('combobox')[0]
        expect(portSelect.value).toBe('/dev/ttyACM0')
      })

      const connectBtn = screen.getByRole('button', { name: /views\.flightController\.connect/ })
      await act(async () => {
        fireEvent.click(connectBtn)
      })

      await waitFor(() => {
        expect(mockShowToast).toHaveBeenCalledWith(
          'views.flightController.connectSuccess',
          'success'
        )
      })
    })

    it('shows error toast on connect failure', async () => {
      mockFetchWithTimeout.mockImplementation((url) => {
        if (url.includes('/api/system/ports')) {
          return Promise.resolve(jsonResponse(portsResponse))
        }
        if (url.includes('/api/mavlink/preferences')) {
          return Promise.resolve(jsonResponse(preferencesResponse))
        }
        if (url.includes('/api/mavlink/connect')) {
          return Promise.resolve(jsonResponse({ success: false, message: 'Port busy' }, false))
        }
        return Promise.resolve(jsonResponse({}))
      })

      await renderView()

      await waitFor(() => {
        const portSelect = screen.getAllByRole('combobox')[0]
        expect(portSelect.value).toBe('/dev/ttyACM0')
      })

      const connectBtn = screen.getByRole('button', { name: /views\.flightController\.connect/ })
      await act(async () => {
        fireEvent.click(connectBtn)
      })

      await waitFor(() => {
        expect(mockShowToast).toHaveBeenCalledWith(
          expect.stringContaining('views.flightController.connectError'),
          'error'
        )
      })
    })

    it('disables connect button when no port available', async () => {
      mockFetchWithTimeout.mockImplementation((url) => {
        if (url.includes('/api/system/ports')) {
          return Promise.resolve(jsonResponse(emptyPortsResponse))
        }
        if (url.includes('/api/mavlink/preferences')) {
          return Promise.resolve(jsonResponse(preferencesDefaultResponse))
        }
        return Promise.resolve(jsonResponse({}))
      })

      await renderView()

      await waitFor(() => {
        const connectBtn = screen.getByText(/views.flightController.connect/).closest('button')
        expect(connectBtn).toBeDisabled()
      })
    })
  })

  describe('Disconnect flow', () => {
    it('shows success toast on disconnect', async () => {
      // Simulate connected state via WebSocket
      mockMessages.mavlink_status = { connected: true }
      setupDefaultMocks()
      await renderView()

      await waitFor(() => {
        expect(screen.getByText(/views.flightController.disconnect$/)).toBeInTheDocument()
      })

      await act(async () => {
        fireEvent.click(screen.getByText(/views.flightController.disconnect$/))
      })

      await waitFor(() => {
        expect(mockShowToast).toHaveBeenCalledWith(
          'views.flightController.disconnectSuccess',
          'success'
        )
      })
    })
  })

  describe('Auto-connect toggle', () => {
    it('renders auto-connect toggle from preferences', async () => {
      setupDefaultMocks()
      await renderView()

      await waitFor(() => {
        const toggle = screen.getByTestId('auto-connect-toggle')
        expect(toggle).toBeInTheDocument()
        expect(toggle.checked).toBe(false)
      })
    })

    it('saves preferences when toggled', async () => {
      setupDefaultMocks()
      // Add mock for preferences POST
      mockFetchWithTimeout.mockImplementation((url, options) => {
        if (url.includes('/api/system/ports')) {
          return Promise.resolve(jsonResponse(portsResponse))
        }
        if (url.includes('/api/mavlink/preferences') && options?.method === 'POST') {
          const body = JSON.parse(options.body)
          return Promise.resolve(
            jsonResponse({
              success: true,
              preferences: body,
            })
          )
        }
        if (url.includes('/api/mavlink/preferences')) {
          return Promise.resolve(jsonResponse(preferencesDefaultResponse))
        }
        return Promise.resolve(jsonResponse({}))
      })

      await renderView()

      await waitFor(() => {
        expect(screen.getByTestId('auto-connect-toggle')).toBeInTheDocument()
      })

      await act(async () => {
        fireEvent.click(screen.getByTestId('auto-connect-toggle'))
      })

      await waitFor(() => {
        const postCall = mockFetchWithTimeout.mock.calls.find(
          (c) => c[0].includes('/api/mavlink/preferences') && c[1]?.method === 'POST'
        )
        expect(postCall).toBeDefined()
      })
    })
  })

  describe('Parameters', () => {
    it('renders base params section', async () => {
      setupDefaultMocks()
      await renderView()

      await waitFor(() => {
        expect(screen.getByText(/views\.flightController\.baseParams/)).toBeInTheDocument()
      })
    })

    it('renders stream rates section', async () => {
      setupDefaultMocks()
      await renderView()

      await waitFor(() => {
        const headings = screen.getAllByRole('heading', { level: 3 })
        const streamHeading = headings.find((h) =>
          h.textContent.includes('views.flightController.streamRates')
        )
        expect(streamHeading).toBeTruthy()
      })
    })

    it('renders vehicle detection message when not connected', async () => {
      setupDefaultMocks()
      await renderView()

      await waitFor(() => {
        expect(screen.getByText('views.flightController.selectVehicleType')).toBeInTheDocument()
      })
    })

    it('auto-loads params when connected and vehicle type detected', async () => {
      mockMessages.mavlink_status = { connected: true }
      mockMessages.telemetry = { system: { vehicle_type: 'QUADROTOR' } }
      setupDefaultMocks()
      await renderView()

      await waitFor(() => {
        const batchCall = mockFetchWithTimeout.mock.calls.find((c) =>
          c[0].includes('/api/mavlink/params/batch/get')
        )
        expect(batchCall).toBeDefined()
      })
    })

    it('shows vehicle-specific params for copter', async () => {
      mockMessages.mavlink_status = { connected: true }
      mockMessages.telemetry = { system: { vehicle_type: 'QUADROTOR' } }
      setupDefaultMocks()
      await renderView()

      await waitFor(() => {
        expect(screen.getByText('views.flightController.vehicleTitle.copter')).toBeInTheDocument()
      })
    })

    it('shows vehicle-specific params for plane', async () => {
      mockMessages.mavlink_status = { connected: true }
      mockMessages.telemetry = { system: { vehicle_type: 'FIXED_WING' } }
      setupDefaultMocks()
      await renderView()

      await waitFor(() => {
        expect(screen.getByText('views.flightController.vehicleTitle.plane')).toBeInTheDocument()
      })
    })
  })

  describe('Save params', () => {
    it('shows save button when params are modified', async () => {
      mockMessages.mavlink_status = { connected: true }
      mockMessages.telemetry = { system: { vehicle_type: 'QUADROTOR' } }
      setupDefaultMocks()
      await renderView()

      // Wait for params to load
      await waitFor(() => {
        const batchCall = mockFetchWithTimeout.mock.calls.find((c) =>
          c[0].includes('/api/mavlink/params/batch/get')
        )
        expect(batchCall).toBeDefined()
      })

      // Change a parameter value via select
      const selects = screen.getAllByRole('combobox')
      // Find the RC_PROTOCOLS select (first param select after port/baudrate)
      const rcProtocolSelect = selects.find((s) => s.closest('.param-item') !== null)

      if (rcProtocolSelect) {
        await act(async () => {
          fireEvent.change(rcProtocolSelect, { target: { value: '256' } })
        })

        await waitFor(() => {
          expect(screen.getByText(/views.flightController.saveChanges/)).toBeInTheDocument()
        })
      }
    })
  })

  describe('Apply recommended', () => {
    it('opens modal on apply recommended click', async () => {
      mockMessages.mavlink_status = { connected: true }
      mockMessages.telemetry = { system: { vehicle_type: 'QUADROTOR' } }
      setupDefaultMocks()
      await renderView()

      // Wait for params to load
      await waitFor(() => {
        const batchCall = mockFetchWithTimeout.mock.calls.find((c) =>
          c[0].includes('/api/mavlink/params/batch/get')
        )
        expect(batchCall).toBeDefined()
      })

      const applyBtn = screen.getByText(/views.flightController.applyRecommended/).closest('button')
      await act(async () => {
        fireEvent.click(applyBtn)
      })

      expect(mockShowModal).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'confirm',
          onConfirm: expect.any(Function),
        })
      )
    })

    it('sends recommended params batch on modal confirm', async () => {
      mockMessages.mavlink_status = { connected: true }
      mockMessages.telemetry = { system: { vehicle_type: 'QUADROTOR' } }
      setupDefaultMocks()
      await renderView()

      // Wait for params to load
      await waitFor(() => {
        const batchCall = mockFetchWithTimeout.mock.calls.find((c) =>
          c[0].includes('/api/mavlink/params/batch/get')
        )
        expect(batchCall).toBeDefined()
      })

      const applyBtn = screen.getByText(/views.flightController.applyRecommended/).closest('button')
      await act(async () => {
        fireEvent.click(applyBtn)
      })

      // Get the onConfirm callback and call it
      const modalCall = mockShowModal.mock.calls[0][0]
      await act(async () => {
        await modalCall.onConfirm()
      })

      await waitFor(() => {
        const setCall = mockFetchWithTimeout.mock.calls.find((c) =>
          c[0].includes('/api/mavlink/params/batch/set')
        )
        expect(setCall).toBeDefined()
        const body = JSON.parse(setCall[1].body)
        // Should include base params recommended values
        expect(body.params).toHaveProperty('RC_PROTOCOLS', 0)
        expect(body.params).toHaveProperty('FS_GCS_ENABL', 1)
        // Stream rates
        expect(body.params).toHaveProperty('SR0_EXTRA1', 4)
        expect(body.params).toHaveProperty('SR0_POSITION', 2)
      })
    })
  })

  describe('Baudrate', () => {
    it('renders all baudrate options', async () => {
      setupDefaultMocks()
      await renderView()

      await waitFor(() => {
        const baudrateSelect = screen.getAllByRole('combobox')[1]
        const options = baudrateSelect.querySelectorAll('option')
        expect(options.length).toBe(8)
      })
    })

    it('marks 115200 as recommended', async () => {
      setupDefaultMocks()
      await renderView()

      await waitFor(() => {
        expect(
          screen.getByText(/115200.*views.flightController.baudrateRecommended/)
        ).toBeInTheDocument()
      })
    })
  })

  describe('Param key correctness', () => {
    it('uses FS_GCS_ENABL (correct ArduPilot parameter name)', async () => {
      // Verify the constants file has the correct key per ArduPilot docs
      const { BASE_PARAMS } = await import('./flightControllerConstants')
      expect(BASE_PARAMS).toHaveProperty('FS_GCS_ENABL')
      expect(BASE_PARAMS).not.toHaveProperty('FS_GCS_ENABLE')
    })
  })

  describe('Not connected state', () => {
    it('disables apply recommended when disconnected', async () => {
      setupDefaultMocks()
      await renderView()

      await waitFor(() => {
        const applyBtn = screen
          .getByText(/views.flightController.applyRecommended/)
          .closest('button')
        expect(applyBtn).toBeDisabled()
      })
    })
  })
})
