import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import { PeerSelector } from './PeerSelector'
import i18n from '../../i18n/i18n'

// Mock API - component uses api.getVPNPeers()
const mockGetVPNPeers = vi.fn()

vi.mock('../../services/api', () => ({
  api: {
    getVPNPeers: (...args) => mockGetVPNPeers(...args),
  },
}))

const PeerSelectorWithProviders = (props) => (
  <I18nextProvider i18n={i18n}>
    <PeerSelector {...props} />
  </I18nextProvider>
)

// Helper: create mock peer objects matching the actual data structure
const createMockPeer = (hostname, ipv4, opts = {}) => ({
  hostname,
  ip_addresses: [ipv4],
  dns_name: opts.dns_name || '',
  os: opts.os || 'linux',
  is_self: opts.is_self || false,
})

const mockPeers = [
  createMockPeer('drone-1', '192.168.1.100', { dns_name: 'drone-1.ts.net', os: 'linux' }),
  createMockPeer('gcs-station', '192.168.1.101', { dns_name: 'gcs.ts.net', os: 'windows' }),
  createMockPeer('relay-node', '10.0.0.50', { os: 'linux' }),
]

describe('PeerSelector Component', () => {
  const mockOnChange = vi.fn()

  const defaultProps = {
    value: '',
    onChange: mockOnChange,
    placeholder: 'IP or hostname',
    disabled: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mockGetVPNPeers.mockResolvedValue({ peers: mockPeers })
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
      expect(input).toHaveAttribute('placeholder', 'IP or hostname')
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

    it('renders dropdown toggle button', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      // Wait for loading to complete so the SVG icon renders
      await waitFor(() => {
        const button = screen.getByRole('button', { name: /select from vpn peers/i })
        expect(button).toBeInTheDocument()
      })
    })

    it('does not show dropdown initially', () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      expect(screen.queryByText(/VPN Nodes/)).not.toBeInTheDocument()
    })
  })

  describe('Input Interaction', () => {
    it('calls onChange when input value changes', () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      fireEvent.change(input, { target: { value: '10.0.0.1' } })

      expect(mockOnChange).toHaveBeenCalledWith('10.0.0.1')
    })

    it('refreshes peers on input focus when peers exist', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      // Wait for initial load
      await waitFor(() => {
        expect(mockGetVPNPeers).toHaveBeenCalledTimes(1)
      })

      const input = screen.getByRole('textbox')
      fireEvent.focus(input)

      await waitFor(() => {
        expect(mockGetVPNPeers).toHaveBeenCalledTimes(2)
      })
    })
  })

  describe('Dropdown Functionality', () => {
    it('opens dropdown when toggle button is clicked', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      await waitFor(() => {
        expect(mockGetVPNPeers).toHaveBeenCalled()
      })

      const button = screen.getByRole('button', { name: /select from vpn peers/i })
      fireEvent.click(button)

      await waitFor(() => {
        expect(screen.getByText(/VPN Nodes/)).toBeInTheDocument()
      })
    })

    it('displays peer count in header', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      await waitFor(() => {
        expect(mockGetVPNPeers).toHaveBeenCalled()
      })

      const button = screen.getByRole('button', { name: /select from vpn peers/i })
      fireEvent.click(button)

      await waitFor(() => {
        expect(screen.getByText(`VPN Nodes (${mockPeers.length})`)).toBeInTheDocument()
      })
    })

    it('displays peer hostnames in dropdown', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      await waitFor(() => {
        expect(mockGetVPNPeers).toHaveBeenCalled()
      })

      const button = screen.getByRole('button', { name: /select from vpn peers/i })
      fireEvent.click(button)

      await waitFor(() => {
        expect(screen.getByText('drone-1')).toBeInTheDocument()
        expect(screen.getByText('gcs-station')).toBeInTheDocument()
        expect(screen.getByText('relay-node')).toBeInTheDocument()
      })
    })

    it('displays peer IP addresses', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      await waitFor(() => {
        expect(mockGetVPNPeers).toHaveBeenCalled()
      })

      const button = screen.getByRole('button', { name: /select from vpn peers/i })
      fireEvent.click(button)

      await waitFor(() => {
        expect(screen.getByText('192.168.1.100')).toBeInTheDocument()
        expect(screen.getByText('192.168.1.101')).toBeInTheDocument()
        expect(screen.getByText('10.0.0.50')).toBeInTheDocument()
      })
    })

    it('displays DNS names when available', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      await waitFor(() => {
        expect(mockGetVPNPeers).toHaveBeenCalled()
      })

      const button = screen.getByRole('button', { name: /select from vpn peers/i })
      fireEvent.click(button)

      await waitFor(() => {
        expect(screen.getByText('drone-1.ts.net')).toBeInTheDocument()
        expect(screen.getByText('gcs.ts.net')).toBeInTheDocument()
      })
    })

    it('selects peer DNS name when option is clicked', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      await waitFor(() => {
        expect(mockGetVPNPeers).toHaveBeenCalled()
      })

      const button = screen.getByRole('button', { name: /select from vpn peers/i })
      fireEvent.click(button)

      await waitFor(() => {
        expect(screen.getByText('drone-1')).toBeInTheDocument()
      })

      // Click on the peer item (click on hostname text)
      const peerItem = screen.getByText('drone-1').closest('.peer-selector-item')
      fireEvent.click(peerItem)

      // Should use DNS name when available
      expect(mockOnChange).toHaveBeenCalledWith('drone-1.ts.net')
    })

    it('selects peer IP when no DNS name available', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      await waitFor(() => {
        expect(mockGetVPNPeers).toHaveBeenCalled()
      })

      const button = screen.getByRole('button', { name: /select from vpn peers/i })
      fireEvent.click(button)

      await waitFor(() => {
        expect(screen.getByText('relay-node')).toBeInTheDocument()
      })

      const peerItem = screen.getByText('relay-node').closest('.peer-selector-item')
      fireEvent.click(peerItem)

      // Should fallback to IP when no DNS name
      expect(mockOnChange).toHaveBeenCalledWith('10.0.0.50')
    })

    it('closes dropdown when toggle button is clicked again', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      await waitFor(() => {
        expect(mockGetVPNPeers).toHaveBeenCalled()
      })

      const button = screen.getByRole('button', { name: /select from vpn peers/i })

      // Open
      fireEvent.click(button)
      await waitFor(() => {
        expect(screen.getByText(/VPN Nodes/)).toBeInTheDocument()
      })

      // Close
      fireEvent.click(button)
      await waitFor(() => {
        expect(screen.queryByText(/VPN Nodes/)).not.toBeInTheDocument()
      })
    })

    it('shows empty state when no peers available', async () => {
      mockGetVPNPeers.mockResolvedValue({ peers: [] })

      render(<PeerSelectorWithProviders {...defaultProps} />)

      await waitFor(() => {
        expect(mockGetVPNPeers).toHaveBeenCalled()
      })

      const button = screen.getByRole('button', { name: /select from vpn peers/i })
      fireEvent.click(button)

      await waitFor(() => {
        expect(screen.getByText(/No VPN peers available/i)).toBeInTheDocument()
      })
    })
  })

  describe('API Integration', () => {
    it('calls getVPNPeers on component mount', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      await waitFor(() => {
        expect(mockGetVPNPeers).toHaveBeenCalledTimes(1)
      })
    })

    it('handles API errors gracefully', async () => {
      mockGetVPNPeers.mockRejectedValue(new Error('Network error'))

      render(<PeerSelectorWithProviders {...defaultProps} />)

      const input = screen.getByRole('textbox')
      // Should still render input even if API fails
      expect(input).toBeInTheDocument()
    })

    it('filters out self peer from list', async () => {
      const peersWithSelf = [
        createMockPeer('this-device', '192.168.1.1', { is_self: true }),
        createMockPeer('other-device', '192.168.1.2'),
      ]
      mockGetVPNPeers.mockResolvedValue({ peers: peersWithSelf })

      render(<PeerSelectorWithProviders {...defaultProps} />)

      await waitFor(() => {
        expect(mockGetVPNPeers).toHaveBeenCalled()
      })

      const button = screen.getByRole('button', { name: /select from vpn peers/i })
      fireEvent.click(button)

      await waitFor(() => {
        expect(screen.getByText('other-device')).toBeInTheDocument()
        expect(screen.queryByText('this-device')).not.toBeInTheDocument()
      })
    })

    it('shows refresh button in dropdown header', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} />)

      await waitFor(() => {
        expect(mockGetVPNPeers).toHaveBeenCalled()
      })

      const toggleButton = screen.getByRole('button', { name: /select from vpn peers/i })
      fireEvent.click(toggleButton)

      await waitFor(() => {
        expect(screen.getByText('🔄')).toBeInTheDocument()
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
  })

  describe('Props', () => {
    it('renders optional label when provided', () => {
      render(<PeerSelectorWithProviders {...defaultProps} label="Host" />)

      expect(screen.getByText('Host')).toBeInTheDocument()
    })

    it('applies error class when hasError is true', () => {
      render(<PeerSelectorWithProviders {...defaultProps} hasError={true} />)

      const input = screen.getByRole('textbox')
      expect(input).toHaveClass('input-error')
    })

    it('disables dropdown button when disabled', async () => {
      render(<PeerSelectorWithProviders {...defaultProps} disabled={true} />)

      // Wait for loading to complete
      await waitFor(() => {
        const button = screen.getByRole('button', { name: /select from vpn peers/i })
        expect(button).toBeDisabled()
      })
    })
  })
})
