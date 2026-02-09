/**
 * VideoView Component Tests
 *
 * Real tests for the VideoView orchestrator component.
 * Sub-component logic is tested in video/SubComponents.test.jsx.
 * Helper functions are tested in video/videoConstants.test.js.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

// ---------- Hoisted mocks (accessible inside vi.mock factories) ----------
const { mockMessages, mockApi } = vi.hoisted(() => {
  const routeData = {
    '/api/video/cameras': { cameras: [] },
    '/api/video/codecs': { codecs: [] },
    '/api/video/network/ip': { ip: '127.0.0.1', rtsp_url: 'rtsp://127.0.0.1:8554/stream' },
  }
  return {
    mockMessages: { video_status: null },
    mockApi: {
      get: vi.fn((url) =>
        Promise.resolve({
          ok: true,
          json: async () => routeData[url] || {},
        })
      ),
      post: vi.fn().mockResolvedValue({ ok: true, json: async () => ({ success: true }) }),
    },
  }
})

// ---------- Mock contexts ----------
vi.mock('../../../contexts/WebSocketContext', () => ({
  useWebSocket: () => ({ messages: mockMessages }),
}))
vi.mock('../../../contexts/ToastContext', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, fallback) => (typeof fallback === 'string' ? fallback : key),
  }),
}))

// ---------- Mock api service ----------
vi.mock('../../../services/api', () => ({ default: mockApi }))

// ---------- Stub sub-components (tested individually) ----------
vi.mock('./video/StatusBanner', () => ({ default: () => <div data-testid="status-banner" /> }))
vi.mock('./video/VideoSourceCard', () => ({
  default: () => <div data-testid="video-source-card" />,
}))
vi.mock('./video/EncodingConfigCard', () => ({
  default: () => <div data-testid="encoding-card" />,
}))
vi.mock('./video/NetworkSettingsCard', () => ({
  default: () => <div data-testid="network-card" />,
}))
vi.mock('./video/StreamControlCard', () => ({
  default: () => <div data-testid="stream-control" />,
}))
vi.mock('./video/PipelineCard', () => ({ default: () => <div data-testid="pipeline-card" /> }))
vi.mock('./video/StatsCard', () => ({ default: () => <div data-testid="stats-card" /> }))

import VideoView from './VideoView'

beforeEach(() => {
  vi.clearAllMocks()
  mockMessages.video_status = null
})

describe('VideoView Component', () => {
  describe('Module', () => {
    it('exports a valid React component named VideoView', () => {
      expect(VideoView).toBeDefined()
      expect(typeof VideoView).toBe('function')
      expect(VideoView.name).toBe('VideoView')
    })
  })

  describe('Rendering', () => {
    it('renders all sub-component slots', async () => {
      // GStreamer must be available for the main UI to render
      mockMessages.video_status = {
        available: true,
        streaming: false,
        enabled: true,
        config: {},
        stats: {},
        last_error: null,
        pipeline_string: '',
      }
      render(<VideoView />)
      await waitFor(() => {
        expect(screen.getByTestId('status-banner')).toBeInTheDocument()
        expect(screen.getByTestId('video-source-card')).toBeInTheDocument()
        expect(screen.getByTestId('encoding-card')).toBeInTheDocument()
        expect(screen.getByTestId('network-card')).toBeInTheDocument()
        expect(screen.getByTestId('stream-control')).toBeInTheDocument()
      })
      // Pipeline and Stats cards only appear when streaming
      expect(screen.queryByTestId('pipeline-card')).not.toBeInTheDocument()
      expect(screen.queryByTestId('stats-card')).not.toBeInTheDocument()
    })

    it('shows gstreamer error when not available', async () => {
      mockMessages.video_status = { available: false, streaming: false }
      render(<VideoView />)
      await waitFor(() => {
        expect(screen.getByText('views.video.gstreamerNotAvailable')).toBeInTheDocument()
      })
    })

    it('shows stats card only when streaming', async () => {
      // Available but not streaming — no stats card
      mockMessages.video_status = {
        available: true,
        streaming: false,
        enabled: true,
        config: {},
        stats: {},
        last_error: null,
        pipeline_string: '',
      }
      const { rerender } = render(<VideoView />)
      await waitFor(() => {
        expect(screen.getByTestId('status-banner')).toBeInTheDocument()
      })
      expect(screen.queryByTestId('stats-card')).not.toBeInTheDocument()

      // Simulate streaming status with stats
      mockMessages.video_status = {
        available: true,
        streaming: true,
        enabled: true,
        config: {},
        stats: { uptime: 10 },
        last_error: null,
        pipeline_string: 'fakepipeline',
      }
      rerender(<VideoView />)
      await waitFor(() => {
        expect(screen.getByTestId('stats-card')).toBeInTheDocument()
      })
    })
  })

  describe('Data Loading', () => {
    it('calls /api/video/cameras on mount', async () => {
      render(<VideoView />)
      await waitFor(() => {
        expect(mockApi.get).toHaveBeenCalledWith('/api/video/cameras')
      })
    })

    it('calls /api/video/codecs on mount', async () => {
      render(<VideoView />)
      await waitFor(() => {
        expect(mockApi.get).toHaveBeenCalledWith('/api/video/codecs')
      })
    })

    it('calls /api/video/network/ip on mount', async () => {
      render(<VideoView />)
      await waitFor(() => {
        expect(mockApi.get).toHaveBeenCalledWith('/api/video/network/ip')
      })
    })
  })
})
