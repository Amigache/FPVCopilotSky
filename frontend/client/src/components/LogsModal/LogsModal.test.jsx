/**
 * LogsModal Component Tests
 *
 * Tests for the optimized LogsModal component that prevents
 * continuous refresh and intermittent spinner display.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import LogsModal from './LogsModal'

// Mock the useTranslation hook
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, defaultValue) => defaultValue || key,
  }),
}))

describe('LogsModal Component - Optimized Behavior', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('loads logs only once when opened', async () => {
    const mockOnRefresh = vi.fn().mockResolvedValue('Mock logs content')
    const mockOnClose = vi.fn()

    render(<LogsModal show={true} onClose={mockOnClose} type="backend" onRefresh={mockOnRefresh} />)

    // Wait for initial load
    await waitFor(() => {
      expect(mockOnRefresh).toHaveBeenCalledTimes(1)
    })
  })

  it('does not reload when props change but modal stays open', async () => {
    const mockOnRefresh = vi.fn().mockResolvedValue('Mock logs')
    const mockOnClose = vi.fn()

    const { rerender } = render(
      <LogsModal show={true} onClose={mockOnClose} type="backend" onRefresh={mockOnRefresh} />
    )

    // Wait for initial load
    await waitFor(() => {
      expect(mockOnRefresh).toHaveBeenCalledTimes(1)
    })

    // Rerender with same props
    rerender(
      <LogsModal show={true} onClose={mockOnClose} type="backend" onRefresh={mockOnRefresh} />
    )

    // Should NOT call onRefresh again (cache prevents it)
    expect(mockOnRefresh).toHaveBeenCalledTimes(1)
  })

  it('reloads when type changes (backend to frontend)', async () => {
    const mockOnRefresh = vi.fn().mockResolvedValue('Mock logs')
    const mockOnClose = vi.fn()

    const { rerender } = render(
      <LogsModal show={true} onClose={mockOnClose} type="backend" onRefresh={mockOnRefresh} />
    )

    await waitFor(() => {
      expect(mockOnRefresh).toHaveBeenCalledTimes(1)
    })

    // Wait for throttle timeout (500ms)
    await new Promise((resolve) => setTimeout(resolve, 600))

    // Change type
    rerender(
      <LogsModal show={true} onClose={mockOnClose} type="frontend" onRefresh={mockOnRefresh} />
    )

    // Should reload with new type
    await waitFor(
      () => {
        expect(mockOnRefresh).toHaveBeenCalledTimes(2)
      },
      { timeout: 2000 }
    )
  })

  it('shows spinner only on initial load', async () => {
    const mockOnRefresh = vi
      .fn()
      .mockImplementation(() => new Promise((resolve) => setTimeout(() => resolve('Logs'), 100)))
    const mockOnClose = vi.fn()

    render(<LogsModal show={true} onClose={mockOnClose} type="backend" onRefresh={mockOnRefresh} />)

    // Spinner should be visible initially
    const spinner = document.querySelector('.logs-spinner')
    expect(spinner).toBeTruthy()

    // Wait for load to complete
    await waitFor(() => {
      const content = document.querySelector('.logs-content')
      expect(content).toBeTruthy()
    })

    // Spinner should be gone
    const spinnerAfter = document.querySelector('.logs-spinner')
    expect(spinnerAfter).toBeFalsy()
  })

  it('manual refresh does not show spinner', async () => {
    const mockOnRefresh = vi.fn().mockResolvedValue('Updated logs')
    const mockOnClose = vi.fn()

    render(<LogsModal show={true} onClose={mockOnClose} type="backend" onRefresh={mockOnRefresh} />)

    // Wait for initial load
    await waitFor(() => {
      const content = document.querySelector('.logs-content')
      expect(content).toBeTruthy()
    })

    // Wait for throttle timeout (500ms)
    await new Promise((resolve) => setTimeout(resolve, 600))

    // Click refresh button
    const refreshButton = screen.getByTitle(/refresh/i) || screen.getByText('🔄')
    fireEvent.click(refreshButton)

    // Content should update without showing spinner
    await waitFor(
      () => {
        expect(mockOnRefresh).toHaveBeenCalledTimes(2)
      },
      { timeout: 2000 }
    )

    // Spinner should NOT appear
    const spinner = document.querySelector('.logs-spinner')
    expect(spinner).toBeFalsy()
  })

  it('throttles rapid refresh attempts', async () => {
    const mockOnRefresh = vi.fn().mockResolvedValue('Logs')
    const mockOnClose = vi.fn()

    render(<LogsModal show={true} onClose={mockOnClose} type="backend" onRefresh={mockOnRefresh} />)

    await waitFor(() => {
      expect(mockOnRefresh).toHaveBeenCalledTimes(1)
    })

    // Click refresh multiple times rapidly
    const refreshButton = screen.getByTitle(/refresh/i) || screen.getByText('🔄')

    fireEvent.click(refreshButton)
    fireEvent.click(refreshButton)
    fireEvent.click(refreshButton)

    // Should be throttled (not called 3 more times)
    await waitFor(() => {
      // May be called 2 times total at most due to throttle
      expect(mockOnRefresh.mock.calls.length).toBeLessThanOrEqual(2)
    })
  })

  it('does not render when show is false', () => {
    const mockOnRefresh = vi.fn()
    const mockOnClose = vi.fn()

    const { container } = render(
      <LogsModal show={false} onClose={mockOnClose} type="backend" onRefresh={mockOnRefresh} />
    )

    // Should return null (not render)
    expect(container.firstChild).toBeFalsy()
    expect(mockOnRefresh).not.toHaveBeenCalled()
  })

  it('handles copy button click', async () => {
    const mockOnRefresh = vi.fn().mockResolvedValue('Logs to copy')
    const mockOnClose = vi.fn()

    // Mock clipboard API
    Object.defineProperty(navigator, 'clipboard', {
      value: {
        writeText: vi.fn(),
      },
      writable: true,
    })

    render(<LogsModal show={true} onClose={mockOnClose} type="backend" onRefresh={mockOnRefresh} />)

    await waitFor(() => {
      expect(mockOnRefresh).toHaveBeenCalled()
    })

    // Click copy button
    const copyButton = screen.getByTitle(/copy/i) || screen.getByText('📋')
    fireEvent.click(copyButton)

    // Should attempt to copy to clipboard
    expect(() => fireEvent.click(copyButton)).not.toThrow()
  })

  it('handles scroll to top button', async () => {
    const mockOnRefresh = vi.fn().mockResolvedValue('Long logs\n'.repeat(100))
    const mockOnClose = vi.fn()

    render(<LogsModal show={true} onClose={mockOnClose} type="backend" onRefresh={mockOnRefresh} />)

    await waitFor(() => {
      expect(mockOnRefresh).toHaveBeenCalled()
    })

    const scrollTopButton = screen.getByTitle(/scroll.*top/i) || screen.getByText('⬆️')

    // Should not throw error
    expect(() => fireEvent.click(scrollTopButton)).not.toThrow()
  })

  it('handles scroll to bottom button', async () => {
    const mockOnRefresh = vi.fn().mockResolvedValue('Long logs\n'.repeat(100))
    const mockOnClose = vi.fn()

    render(<LogsModal show={true} onClose={mockOnClose} type="backend" onRefresh={mockOnRefresh} />)

    await waitFor(() => {
      expect(mockOnRefresh).toHaveBeenCalled()
    })

    const scrollBottomButton = screen.getByTitle(/scroll.*bottom/i) || screen.getByText('⬇️')

    // Should not throw error
    expect(() => fireEvent.click(scrollBottomButton)).not.toThrow()
  })

  it('displays error message when onRefresh fails', async () => {
    const mockOnRefresh = vi.fn().mockRejectedValue(new Error('Failed to load'))
    const mockOnClose = vi.fn()

    render(<LogsModal show={true} onClose={mockOnClose} type="backend" onRefresh={mockOnRefresh} />)

    // Should show error in logs content
    await waitFor(() => {
      const content = screen.getByText(/error/i) || screen.getByText(/status.logs.errorLoading/i)
      expect(content).toBeTruthy()
    })
  })
})
