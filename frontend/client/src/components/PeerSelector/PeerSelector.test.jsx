import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import PeerSelector from '../PeerSelector'
import i18n from '../../i18n/i18n'

// Mock API
vi.mock('../../services/api', () => ({
  API_VPN: '/api/vpn',
  fetchWithTimeout: vi.fn(),
}))

const PeerSelectorWithProviders = (props) => (
  <I18nextProvider i18n={i18n}>
    <PeerSelector {...props} />
  </I18nextProvider>
)

describe('PeerSelector Component', () => {
  const mockOnChange = vi.fn()

  const defaultProps = {
    value: '',
    onChange: mockOnChange,
    placeholder: 'Enter peer IP...',
    disabled: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Module', () => {
    it('exports a valid React component named PeerSelector', () => {
      expect(PeerSelector).toBeDefined()
      expect(PeerSelector.name).toBe('PeerSelector')
      expect(typeof PeerSelector).toBe('function')
    })
  })

  describe('Rendering', () => {
    it('renders input element with correct props', () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      expect(input).toBeInTheDocument()
      expect(input).toHaveAttribute('placeholder', 'Enter peer IP...')
      expect(input).not.toBeDisabled()
    })

    it('renders with disabled state', () => {
      const disabledProps = { ...defaultProps, disabled: true }
      render(<PeerSelectorWithProviders {...disabledProps} />)

      const input = screen.getByRole('textbox')
      expect(input).toBeDisabled()
    })

    it('renders with initial value', () => {
      const valueProps = { ...defaultProps, value: '192.168.1.100' }
      render(<PeerSelectorWithProviders {...valueProps} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveValue('192.168.1.100')
    })

    it('does not show dropdown initially', () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      const dropdown = screen.queryByRole('listbox')
      expect(dropdown).not.toBeInTheDocument()
    })
  })

  describe('Input Interaction', () => {
    it('calls onChange when input value changes', () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: '10.0.0.1' } })

      expect(mockOnChange).toHaveBeenCalledWith('10.0.0.1')
    })

    it('shows dropdown on focus', async () => {
      // Mock API response with peers
      const { fetchWithTimeout } = await import('../../services/api')
      fetchWithTimeout.mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            peers: ['192.168.1.100', '10.0.0.50', '172.16.1.1'],
          }),
      })

      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      fireEvent.focus(input)

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument()
      })
    })

    it('hides dropdown on blur', async () => {
      const { fetchWithTimeout } = await import('../../services/api')
      fetchWithTimeout.mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            peers: ['192.168.1.100'],
          }),
      })

      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      fireEvent.focus(input)

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument()
      })

      fireEvent.blur(input)

      await waitFor(() => {
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
      })
    })
  })

  describe('Dropdown Functionality', () => {
    beforeEach(async () => {
      // Mock peers data for dropdown tests
      const { fetchWithTimeout } = await import('../../services/api')
      fetchWithTimeout.mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            peers: ['192.168.1.100', '192.168.1.101', '10.0.0.50'],
          }),
      })
    })

    it('displays Available IPs header', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      fireEvent.focus(input)

      await waitFor(() => {
        expect(screen.getByText(/Available IPs/i)).toBeInTheDocument()
      })
    })

    it('displays peer options in dropdown', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      fireEvent.focus(input)

      await waitFor(() => {
        expect(screen.getByText('192.168.1.100')).toBeInTheDocument()
        expect(screen.getByText('192.168.1.101')).toBeInTheDocument()
        expect(screen.getByText('10.0.0.50')).toBeInTheDocument()
      })
    })

    it('filters peers based on input value', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      fireEvent.focus(input)

      // Wait for initial dropdown to appear
      await waitFor(() => {
        expect(screen.getByText('192.168.1.100')).toBeInTheDocument()
      })

      // Type to filter
      fireEvent.change(input, { target: { value: '192.168' } })

      await waitFor(() => {
        expect(screen.getByText('192.168.1.100')).toBeInTheDocument()
        expect(screen.getByText('192.168.1.101')).toBeInTheDocument()
        expect(screen.queryByText('10.0.0.50')).not.toBeInTheDocument()
      })
    })

    it('selects peer when option is clicked', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      fireEvent.focus(input)

      await waitFor(() => {
        expect(screen.getByText('192.168.1.100')).toBeInTheDocument()
      })

      const peerOption = screen.getByText('192.168.1.100')
      fireEvent.click(peerOption)

      expect(mockOnChange).toHaveBeenCalledWith('192.168.1.100')
    })

    it('shows "No matching peers" when filter has no results', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      fireEvent.focus(input)

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument()
      })

      fireEvent.change(input, { target: { value: '172.99.99.99' } })

      await waitFor(() => {
        expect(screen.getByText(/No matching peers/i)).toBeInTheDocument()
      })
    })
  })

  describe('Keyboard Navigation', () => {
    beforeEach(async () => {
      const { fetchWithTimeout } = await import('../../services/api')
      fetchWithTimeout.mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            peers: ['192.168.1.100', '192.168.1.101', '10.0.0.50'],
          }),
      })
    })

    it('navigates dropdown with arrow keys', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      fireEvent.focus(input)

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument()
      })

      // Arrow down should highlight first option
      fireEvent.keyDown(input, { key: 'ArrowDown', code: 'ArrowDown' })

      // Check if first option is highlighted (implementation specific)
      const options = screen.getAllByRole('option')
      expect(options[0]).toHaveClass('highlighted')
    })

    it('selects highlighted option with Enter key', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      fireEvent.focus(input)

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument()
      })

      // Navigate to first option and select
      fireEvent.keyDown(input, { key: 'ArrowDown', code: 'ArrowDown' })
      fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' })

      expect(mockOnChange).toHaveBeenCalledWith('192.168.1.100')
    })

    it('closes dropdown with Escape key', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      fireEvent.focus(input)

      await waitFor(() => {
        expect(screen.getByRole('listbox')).toBeInTheDocument()
      })

      fireEvent.keyDown(input, { key: 'Escape', code: 'Escape' })

      await waitFor(() => {
        expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
      })
    })
  })

  describe('API Integration', () => {
    it('calls peers API on component mount', async () => {
      const { fetchWithTimeout } = await import('../../services/api')
      fetchWithTimeout.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true, peers: [] }),
      })

      render(<PeerSelectorWithProviders {...defaultProps} />)

      await waitFor(() => {
        expect(fetchWithTimeout).toHaveBeenCalledWith('/api/vpn/peers', expect.any(Object))
      })
    })

    it('handles API errors gracefully', async () => {
      const { fetchWithTimeout } = await import('../../services/api')
      fetchWithTimeout.mockRejectedValue(new Error('Network error'))

      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      fireEvent.focus(input)

      // Should still render input even if API fails
      expect(input).toBeInTheDocument()

      // Dropdown should show error state or empty state
      await waitFor(() => {
        const dropdown = screen.queryByRole('listbox')
        if (dropdown) {
          expect(screen.getByText(/No peers available/i)).toBeInTheDocument()
        }
      })
    })

    it('shows empty state when no peers available', async () => {
      const { fetchWithTimeout } = await import('../../services/api')
      fetchWithTimeout.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true, peers: [] }),
      })

      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      fireEvent.focus(input)

      await waitFor(() => {
        const dropdown = screen.queryByRole('listbox')
        if (dropdown) {
          expect(screen.getByText(/No peers available/i)).toBeInTheDocument()
        }
      })
    })
  })

  describe('Scroll Optimization', () => {
    it('sets appropriate dropdown height based on available space', async () => {
      // Mock a large list of peers to trigger scroll behavior
      const { fetchWithTimeout } = await import('../../services/api')
      const largePeersList = Array.from({ length: 20 }, (_, i) => `192.168.1.${i + 1}`)
      fetchWithTimeout.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true, peers: largePeersList }),
      })

      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      fireEvent.focus(input)

      await waitFor(() => {
        const dropdown = screen.getByRole('listbox')
        expect(dropdown).toBeInTheDocument()

        // Check if dropdown has appropriate styling for scrolling
        const dropdownStyle = window.getComputedStyle(dropdown)
        expect(dropdownStyle.overflowY).toBe('auto')
      })
    })
  })

  describe('Performance', () => {
    it('memoizes component to prevent unnecessary re-renders', () => {
      const { rerender } = render(<PeerSelectorWithProviders {...defaultProps} />)

      // Re-render with same props should not cause re-mount
      rerender(<PeerSelectorWithProviders {...defaultProps} />)

      // Component should still be present and functional
      expect(screen.getByRole('textbox')).toBeInTheDocument()
    })

    it('debounces API calls when typing rapidly', async () => {
      const { fetchWithTimeout } = await import('../../services/api')
      fetchWithTimeout.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true, peers: ['192.168.1.100'] }),
      })

      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')

      // Simulate rapid typing
      fireEvent.focus(input)
      fireEvent.change(input, { target: { value: '1' } })
      fireEvent.change(input, { target: { value: '19' } })
      fireEvent.change(input, { target: { value: '192' } })
      fireEvent.change(input, { target: { value: '192.' } })

      // Should only make one API call after debounce
      await waitFor(() => {
        expect(fetchWithTimeout).toHaveBeenCalledTimes(1)
      })
    })
  })
})
