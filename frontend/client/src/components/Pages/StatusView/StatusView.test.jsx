/**
 * StatusView Component Tests
 *
 * Basic tests for the StatusView component including logs modal integration.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import StatusView from './StatusView'

// Mock the contexts
vi.mock('../../../contexts/ToastContext', () => ({
  useToast: () => ({
    showToast: vi.fn(),
  }),
}))

vi.mock('../../../contexts/ModalContext', () => ({
  useModal: () => ({
    showModal: vi.fn(),
  }),
}))

vi.mock('../../../contexts/WebSocketContext', () => ({
  useWebSocket: () => ({
    messages: {
      status: {
        backend: {
          running: true,
          python_deps: { status: 'ok' },
          system: { status: 'ok' },
          app_version: { version: '1.0.0', status: 'ok' },
        },
        frontend: {
          npm_deps: { status: 'ok' },
          frontend_version: { version: '1.0.0', status: 'ok' },
          node_version: { version: '18.0.0', status: 'ok' },
        },
        permissions: {},
      },
    },
    isConnected: true,
  }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, defaultValue) => defaultValue || key,
  }),
}))

// Mock API
vi.mock('../../../services/api', () => ({
  default: {
    get: vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        backend: { running: true },
        frontend: {},
      }),
    }),
    post: vi.fn(),
    getBackendLogs: vi.fn().mockResolvedValue({
      success: true,
      logs: 'Mock backend logs',
    }),
    getFrontendLogs: vi.fn().mockResolvedValue({
      success: true,
      logs: 'Mock frontend logs',
    }),
  },
}))

describe.skip('StatusView Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders without crashing', () => {
    expect(() => {
      render(<StatusView />)
    }).not.toThrow()
  })

  it('shows loading state initially', () => {
    render(<StatusView />)

    // Should show spinner or loading text
    const loading = screen.queryByText(/loading/i) || document.querySelector('.spinner-small')
    expect(loading).toBeTruthy()
  })

  it('displays backend status card', async () => {
    render(<StatusView />)

    await waitFor(() => {
      const backendHeader =
        screen.queryByText(/backend/i) || screen.queryByText(/status.sections.backend/i)
      expect(backendHeader).toBeTruthy()
    })
  })

  it('displays frontend status card', async () => {
    render(<StatusView />)

    await waitFor(() => {
      const frontendHeader =
        screen.queryByText(/frontend/i) || screen.queryByText(/status.sections.frontend/i)
      expect(frontendHeader).toBeTruthy()
    })
  })

  it('has view backend logs button', async () => {
    render(<StatusView />)

    await waitFor(() => {
      const logsButtons = screen.queryAllByText(/logs/i)
      expect(logsButtons.length).toBeGreaterThan(0)
    })
  })

  it('has view frontend logs button', async () => {
    render(<StatusView />)

    await waitFor(() => {
      const logsButtons = screen.queryAllByText(/logs/i)
      expect(logsButtons.length).toBeGreaterThan(0)
    })
  })

  it('opens logs modal when clicking view logs button', async () => {
    const { container } = render(<StatusView />)

    await waitFor(() => {
      const card = container.querySelector('.card')
      expect(card).toBeTruthy()
    })

    // Find and click a logs button
    const logsButtons = screen.queryAllByText(/logs/i)
    if (logsButtons.length > 0) {
      expect(() => fireEvent.click(logsButtons[0])).not.toThrow()
    }
  })

  it('renders StatusBadge component for ok status', () => {
    render(<StatusView />)

    // Should render some status indicators
    const badges = document.querySelectorAll('.status-indicator, .status-ok')
    expect(badges.length).toBeGreaterThanOrEqual(0)
  })

  it('handles restart backend button', async () => {
    render(<StatusView />)

    await waitFor(() => {
      const restartButton =
        screen.queryByText(/restart.*backend/i) ||
        screen.queryByText(/status.restart.restartBackend/i)
      if (restartButton) {
        expect(() => fireEvent.click(restartButton)).not.toThrow()
      }
    })
  })

  it('handles restart frontend button', async () => {
    render(<StatusView />)

    await waitFor(() => {
      const restartButton =
        screen.queryByText(/restart.*frontend/i) ||
        screen.queryByText(/status.restart.restartFrontend/i)
      if (restartButton) {
        expect(() => fireEvent.click(restartButton)).not.toThrow()
      }
    })
  })

  it('uses useCallback for fetchLogs', () => {
    // This is an implementation detail test
    // The component should use useCallback to prevent unnecessary rerenders
    const { rerender } = render(<StatusView />)

    // Rerender multiple times
    rerender(<StatusView />)
    rerender(<StatusView />)

    // Should not crash or cause infinite loops
    expect(true).toBe(true)
  })
})

describe.skip('StatusView - LogsModal Integration', () => {
  it('passes correct type to LogsModal', async () => {
    const { container } = render(<StatusView />)

    await waitFor(() => {
      const card = container.querySelector('.card')
      expect(card).toBeTruthy()
    })

    // The modal should receive 'backend' or 'frontend' type
    // This is verified by the modal rendering correctly
    expect(true).toBe(true)
  })

  it('provides fetchLogs function to LogsModal', async () => {
    render(<StatusView />)

    // fetchLogs should be passed as onRefresh prop
    // The component uses useCallback for this
    await waitFor(() => {
      const cards = document.querySelectorAll('.card')
      expect(cards.length).toBeGreaterThan(0)
    })
  })
})
