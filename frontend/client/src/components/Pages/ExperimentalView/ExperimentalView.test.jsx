/**
 * ExperimentalView Component Tests
 *
 * Tests for the ExperimentalView component including OpenCV configuration
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ExperimentalView from './ExperimentalView'

// Hoisted mocks for API
const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

// Mock the contexts
vi.mock('../../../contexts/ToastContext', () => ({
  useToast: () => ({
    showToast: vi.fn(),
  }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
  }),
}))

// Mock API
vi.mock('../../../services/api', () => ({
  default: mockApi,
}))

describe('ExperimentalView Component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default successful responses
    mockApi.get.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        opencv_enabled: false,
        config: {
          filter: 'none',
          osd_enabled: false,
          edgeThreshold1: 100,
          edgeThreshold2: 200,
          blurKernel: 15,
          thresholdValue: 127,
        },
      }),
    })
    mockApi.post.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, opencv_enabled: true }),
    })
  })

  afterEach(() => {
    vi.clearAllTimers()
  })

  describe('Module', () => {
    it('exports a valid React component', () => {
      expect(ExperimentalView).toBeDefined()
      expect(typeof ExperimentalView).toBe('function')
    })
  })

  describe('Initial Rendering', () => {
    it('shows loading state initially', () => {
      render(<ExperimentalView />)
      expect(screen.getByText('common.loading')).toBeInTheDocument()
    })

    it('renders main sections after loading', async () => {
      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.title')).toBeInTheDocument()
      })

      expect(screen.getByText('experimental.opencv.title')).toBeInTheDocument()
      expect(screen.getByText('experimental.info.title')).toBeInTheDocument()
    })

    it('loads configuration on mount', async () => {
      render(<ExperimentalView />)

      await waitFor(() => {
        expect(mockApi.get).toHaveBeenCalledWith('/api/experimental/config')
      })
    })
  })

  describe('OpenCV Toggle', () => {
    it('displays OpenCV status as inactive by default', async () => {
      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.opencv.inactive')).toBeInTheDocument()
      })
    })

    it('displays OpenCV status as active when enabled', async () => {
      mockApi.get.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          opencv_enabled: true,
          config: { filter: 'none', osd_enabled: false },
        }),
      })

      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.opencv.active')).toBeInTheDocument()
      })
    })

    it('calls API when toggling OpenCV on', async () => {
      const user = userEvent.setup()
      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.opencv.title')).toBeInTheDocument()
      })

      const toggleInputs = screen.getAllByTestId('toggle-input')
      const opencvToggle = toggleInputs[0]

      await user.click(opencvToggle)

      await waitFor(() => {
        expect(mockApi.post).toHaveBeenCalledWith('/api/experimental/toggle', {
          enabled: true,
        })
      })
    })

    it('calls video restart after toggling OpenCV', async () => {
      const user = userEvent.setup()
      mockApi.post.mockResolvedValue({
        ok: true,
        json: async () => ({ success: true, opencv_enabled: true }),
      })

      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.opencv.title')).toBeInTheDocument()
      })

      const toggleInputs = screen.getAllByTestId('toggle-input')
      await user.click(toggleInputs[0])

      await waitFor(() => {
        expect(mockApi.post).toHaveBeenCalledWith('/api/video/restart')
      })
    })
  })

  describe('OSD Toggle', () => {
    it('OSD toggle is disabled when OpenCV is off', async () => {
      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.opencv.osdEnabled')).toBeInTheDocument()
      })

      const toggles = screen.getAllByTestId('toggle-input')
      const osdToggle = toggles[1]
      expect(osdToggle).toBeDisabled()
    })

    it('OSD toggle is enabled when OpenCV is on', async () => {
      mockApi.get.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          opencv_enabled: true,
          config: { filter: 'none', osd_enabled: false },
        }),
      })

      render(<ExperimentalView />)

      await waitFor(() => {
        const toggles = screen.getAllByTestId('toggle-input')
        expect(toggles[1]).not.toBeDisabled()
      })
    })

    it('calls API when toggling OSD', async () => {
      const user = userEvent.setup()
      mockApi.get.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          opencv_enabled: true,
          config: { filter: 'none', osd_enabled: false },
        }),
      })

      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.opencv.osdEnabled')).toBeInTheDocument()
      })

      const toggles = screen.getAllByTestId('toggle-input')
      await user.click(toggles[1])

      await waitFor(() => {
        expect(mockApi.post).toHaveBeenCalledWith(
          '/api/experimental/config',
          expect.objectContaining({ osd_enabled: true })
        )
      })
    })
  })

  describe('Filter Selection', () => {
    it('renders filter dropdown', async () => {
      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.opencv.selectFilter')).toBeInTheDocument()
      })

      const select = screen.getByRole('combobox')
      expect(select).toBeInTheDocument()
    })

    it('filter dropdown is disabled when OpenCV is off', async () => {
      render(<ExperimentalView />)

      await waitFor(() => {
        const select = screen.getByRole('combobox')
        expect(select).toBeDisabled()
      })
    })

    it('shows all filter options', async () => {
      mockApi.get.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          opencv_enabled: true,
          config: { filter: 'none', osd_enabled: false },
        }),
      })

      render(<ExperimentalView />)

      await waitFor(() => {
        const select = screen.getByRole('combobox')
        expect(select).not.toBeDisabled()
      })

      const options = screen.getAllByRole('option')
      expect(options.length).toBeGreaterThanOrEqual(6)
    })

    it('calls API when changing filter', async () => {
      const user = userEvent.setup()
      mockApi.get.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          opencv_enabled: true,
          config: { filter: 'none', osd_enabled: false },
        }),
      })

      render(<ExperimentalView />)

      await waitFor(() => {
        const select = screen.getByRole('combobox')
        expect(select).not.toBeDisabled()
      })

      const select = screen.getByRole('combobox')
      await user.selectOptions(select, 'edges')

      await waitFor(() => {
        expect(mockApi.post).toHaveBeenCalledWith(
          '/api/experimental/config',
          expect.objectContaining({ filter: 'edges' })
        )
      })
    })
  })

  describe('Edge Filter Parameters', () => {
    it('shows edge threshold sliders when edges filter is selected', async () => {
      mockApi.get.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          opencv_enabled: true,
          config: { filter: 'edges', osd_enabled: false, edgeThreshold1: 100, edgeThreshold2: 200 },
        }),
      })

      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.opencv.edgeThreshold1')).toBeInTheDocument()
        expect(screen.getByText('experimental.opencv.edgeThreshold2')).toBeInTheDocument()
      })
    })

    it('updates edge threshold1 value', async () => {
      const user = userEvent.setup()
      mockApi.get.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          opencv_enabled: true,
          config: { filter: 'edges', osd_enabled: false, edgeThreshold1: 100, edgeThreshold2: 200 },
        }),
      })

      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.opencv.edgeThreshold1')).toBeInTheDocument()
      })

      const sliders = screen.getAllByRole('slider')
      const threshold1Slider = sliders[0]

      fireEvent.change(threshold1Slider, { target: { value: '150' } })

      await waitFor(() => {
        expect(threshold1Slider.value).toBe('150')
      })
    })
  })

  describe('Blur Filter Parameters', () => {
    it('shows blur kernel slider when blur filter is selected', async () => {
      mockApi.get.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          opencv_enabled: true,
          config: { filter: 'blur', osd_enabled: false, blurKernel: 15 },
        }),
      })

      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.opencv.blurKernel')).toBeInTheDocument()
      })

      const slider = screen.getByRole('slider')
      expect(slider).toHaveAttribute('min', '3')
      expect(slider).toHaveAttribute('max', '31')
      expect(slider).toHaveAttribute('step', '2')
    })

    it('updates blur kernel value', async () => {
      mockApi.get.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          opencv_enabled: true,
          config: { filter: 'blur', osd_enabled: false, blurKernel: 15 },
        }),
      })

      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.opencv.blurKernel')).toBeInTheDocument()
      })

      const slider = screen.getByRole('slider')
      fireEvent.change(slider, { target: { value: '21' } })

      await waitFor(() => {
        expect(slider.value).toBe('21')
      })
    })
  })

  describe('Threshold Filter Parameters', () => {
    it('shows threshold value slider when threshold filter is selected', async () => {
      mockApi.get.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          opencv_enabled: true,
          config: { filter: 'threshold', osd_enabled: false, thresholdValue: 127 },
        }),
      })

      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.opencv.thresholdValue')).toBeInTheDocument()
      })

      const slider = screen.getByRole('slider')
      expect(slider).toHaveAttribute('min', '0')
      expect(slider).toHaveAttribute('max', '255')
    })

    it('updates threshold value', async () => {
      mockApi.get.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          opencv_enabled: true,
          config: { filter: 'threshold', osd_enabled: false, thresholdValue: 127 },
        }),
      })

      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.opencv.thresholdValue')).toBeInTheDocument()
      })

      const slider = screen.getByRole('slider')
      fireEvent.change(slider, { target: { value: '180' } })

      await waitFor(() => {
        expect(slider.value).toBe('180')
      })
    })
  })

  describe('Info Section', () => {
    it('renders info section with future features', async () => {
      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.info.title')).toBeInTheDocument()
      })

      expect(screen.getByText('experimental.future.title')).toBeInTheDocument()
      expect(screen.getByText('experimental.future.objectDetection')).toBeInTheDocument()
      expect(screen.getByText('experimental.future.mlIntegration')).toBeInTheDocument()
      expect(screen.getByText('experimental.future.videoAnalysis')).toBeInTheDocument()
      expect(screen.getByText('experimental.future.featureTracking')).toBeInTheDocument()
    })
  })

  describe('Error Handling', () => {
    it('handles API error when loading config', async () => {
      mockApi.get.mockRejectedValueOnce(new Error('Network error'))

      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.queryByText('common.loading')).not.toBeInTheDocument()
      })

      expect(consoleError).toHaveBeenCalledWith('Error loading config:', expect.any(Error))
      consoleError.mockRestore()
    })

    it('handles API error when toggling OpenCV', async () => {
      const user = userEvent.setup()
      mockApi.post.mockRejectedValueOnce(new Error('Toggle failed'))

      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.opencv.title')).toBeInTheDocument()
      })

      const toggles = screen.getAllByTestId('toggle-input')
      await user.click(toggles[0])

      await waitFor(() => {
        expect(consoleError).toHaveBeenCalled()
      })

      consoleError.mockRestore()
    })

    it('handles unsuccessful response when toggling OpenCV', async () => {
      const user = userEvent.setup()
      mockApi.post.mockResolvedValueOnce({
        ok: false,
        json: async () => ({ message: 'Service unavailable' }),
      })

      render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.opencv.title')).toBeInTheDocument()
      })

      const toggles = screen.getAllByTestId('toggle-input')
      await user.click(toggles[0])

      await waitFor(() => {
        expect(mockApi.post).toHaveBeenCalledWith('/api/experimental/toggle', { enabled: true })
      })
    })
  })

  describe('Cleanup', () => {
    it('clears timeout on unmount', async () => {
      vi.useFakeTimers()

      const { unmount } = render(<ExperimentalView />)

      await waitFor(() => {
        expect(screen.getByText('experimental.title')).toBeInTheDocument()
      })

      const clearTimeoutSpy = vi.spyOn(global, 'clearTimeout')

      unmount()

      expect(clearTimeoutSpy).toHaveBeenCalled()

      vi.useRealTimers()
      clearTimeoutSpy.mockRestore()
    })
  })
})
