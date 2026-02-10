/**
 * WebRTC Component Tests
 *
 * Tests for WebRTCViewerCard and WebRTCLogCard components.
 * These components handle WebRTC video viewer and event logging.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ---------- Mocks ----------

// i18n mock
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, fallback) => (typeof fallback === 'string' ? fallback : key),
  }),
}))

// API mock
vi.mock('../../../services/api', () => ({
  default: {
    post: vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ success: true }),
      })
    ),
    get: vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            video: { maxBitrate: 1500000 },
            ice: { bundlePolicy: 'max-bundle' },
          }),
      })
    ),
  },
}))

import WebRTCLogCard from './WebRTCLogCard'
import WebRTCViewerCard from './WebRTCViewerCard'

// ===========================================================================
// WebRTCLogCard
// ===========================================================================
describe('WebRTCLogCard', () => {
  const emptyStatus = { log: [] }

  const statusWithLogs = {
    log: [
      { timestamp: 1700000000, level: 'info', message: 'Peer abc created' },
      { timestamp: 1700000001, level: 'success', message: 'Peer abc connected' },
      { timestamp: 1700000002, level: 'warning', message: 'High latency detected' },
      { timestamp: 1700000003, level: 'error', message: 'Connection lost' },
    ],
  }

  it('renders the card', () => {
    render(<WebRTCLogCard webrtcStatus={emptyStatus} />)
    expect(screen.getByTestId('webrtc-log-card')).toBeInTheDocument()
  })

  it('shows log title', () => {
    render(<WebRTCLogCard webrtcStatus={emptyStatus} />)
    expect(screen.getByText('views.video.webrtcLog')).toBeInTheDocument()
  })

  it('starts collapsed by default', () => {
    render(<WebRTCLogCard webrtcStatus={statusWithLogs} />)
    // Log entries should not be visible when collapsed
    expect(screen.queryByText('Peer abc created')).not.toBeInTheDocument()
  })

  it('shows entry count badge', () => {
    render(<WebRTCLogCard webrtcStatus={statusWithLogs} />)
    expect(screen.getByText('4')).toBeInTheDocument()
  })

  it('expands when header is clicked', async () => {
    const user = userEvent.setup()
    render(<WebRTCLogCard webrtcStatus={statusWithLogs} />)

    const header = screen.getByRole('button')
    await user.click(header)

    expect(screen.getByText('Peer abc created')).toBeInTheDocument()
    expect(screen.getByText('Peer abc connected')).toBeInTheDocument()
    expect(screen.getByText('High latency detected')).toBeInTheDocument()
    expect(screen.getByText('Connection lost')).toBeInTheDocument()
  })

  it('collapses when clicked again', async () => {
    const user = userEvent.setup()
    render(<WebRTCLogCard webrtcStatus={statusWithLogs} />)

    const header = screen.getByRole('button')
    await user.click(header) // expand
    expect(screen.getByText('Peer abc created')).toBeInTheDocument()

    await user.click(header) // collapse
    expect(screen.queryByText('Peer abc created')).not.toBeInTheDocument()
  })

  it('shows empty message when no logs', async () => {
    const user = userEvent.setup()
    render(<WebRTCLogCard webrtcStatus={emptyStatus} />)

    const header = screen.getByRole('button')
    await user.click(header)

    expect(screen.getByText('views.video.webrtcLogEmpty')).toBeInTheDocument()
  })

  it('handles null webrtcStatus gracefully', () => {
    render(<WebRTCLogCard webrtcStatus={null} />)
    expect(screen.getByTestId('webrtc-log-card')).toBeInTheDocument()
    expect(screen.getByText('0')).toBeInTheDocument()
  })

  it('renders log level icons', async () => {
    const user = userEvent.setup()
    render(<WebRTCLogCard webrtcStatus={statusWithLogs} />)
    await user.click(screen.getByRole('button'))

    // Check level icons are present
    expect(screen.getByText('ℹ️')).toBeInTheDocument()
    expect(screen.getByText('✅')).toBeInTheDocument()
    expect(screen.getByText('⚠️')).toBeInTheDocument()
    expect(screen.getByText('❌')).toBeInTheDocument()
  })

  it('shows toggle arrow indicator', () => {
    render(<WebRTCLogCard webrtcStatus={emptyStatus} />)
    expect(screen.getByText('▼')).toBeInTheDocument()
  })

  it('changes toggle arrow when expanded', async () => {
    const user = userEvent.setup()
    render(<WebRTCLogCard webrtcStatus={emptyStatus} />)

    await user.click(screen.getByRole('button'))
    expect(screen.getByText('▲')).toBeInTheDocument()
  })

  it('expands via keyboard Enter', () => {
    render(<WebRTCLogCard webrtcStatus={statusWithLogs} />)
    const header = screen.getByRole('button')
    fireEvent.keyDown(header, { key: 'Enter' })
    expect(screen.getByText('Peer abc created')).toBeInTheDocument()
  })

  it('expands via keyboard Space', () => {
    render(<WebRTCLogCard webrtcStatus={statusWithLogs} />)
    const header = screen.getByRole('button')
    fireEvent.keyDown(header, { key: ' ' })
    expect(screen.getByText('Peer abc created')).toBeInTheDocument()
  })
})

// ===========================================================================
// WebRTCViewerCard
// ===========================================================================
describe('WebRTCViewerCard', () => {
  const baseStatus = {
    streaming: true,
    config: { mode: 'webrtc' },
  }

  const baseWebrtcStatus = {
    active: true,
    peers: [],
    global_stats: { total_peers: 0, active_peers: 0 },
  }

  it('renders the viewer card', () => {
    render(<WebRTCViewerCard status={baseStatus} webrtcStatus={baseWebrtcStatus} />)
    expect(screen.getByTestId('webrtc-viewer-card')).toBeInTheDocument()
  })

  it('shows viewer title', () => {
    render(<WebRTCViewerCard status={baseStatus} webrtcStatus={baseWebrtcStatus} />)
    expect(screen.getByText('views.video.webrtcViewer')).toBeInTheDocument()
  })

  it('shows disconnected state by default', () => {
    render(<WebRTCViewerCard status={baseStatus} webrtcStatus={baseWebrtcStatus} />)
    expect(screen.getByText('views.video.webrtcState.disconnected')).toBeInTheDocument()
  })

  it('shows connect button when disconnected', () => {
    render(<WebRTCViewerCard status={baseStatus} webrtcStatus={baseWebrtcStatus} />)
    expect(screen.getByText('views.video.webrtcConnect')).toBeInTheDocument()
  })

  it('shows video element', () => {
    render(<WebRTCViewerCard status={baseStatus} webrtcStatus={baseWebrtcStatus} />)
    expect(screen.getByTestId('webrtc-video')).toBeInTheDocument()
  })

  it('shows no-signal overlay when disconnected', () => {
    render(<WebRTCViewerCard status={baseStatus} webrtcStatus={baseWebrtcStatus} />)
    expect(screen.getByText('views.video.webrtcNoSignal')).toBeInTheDocument()
  })

  it('shows fullscreen button', () => {
    render(<WebRTCViewerCard status={baseStatus} webrtcStatus={baseWebrtcStatus} />)
    const fsButton = screen.getByTitle('views.video.webrtcFullscreen')
    expect(fsButton).toBeInTheDocument()
  })

  it('video element has autoPlay and playsInline', () => {
    render(<WebRTCViewerCard status={baseStatus} webrtcStatus={baseWebrtcStatus} />)
    const video = screen.getByTestId('webrtc-video')
    expect(video).toHaveAttribute('autoplay')
    expect(video).toHaveAttribute('playsinline')
  })
})
