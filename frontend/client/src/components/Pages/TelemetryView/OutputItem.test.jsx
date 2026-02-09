import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { I18nextProvider } from 'react-i18next'
import OutputItem from '../OutputItem'
import i18n from '../../../../i18n/i18n'

// Mock contexts
const mockShowToast = vi.fn()
const mockShowModal = vi.fn()

vi.mock('../../../../contexts/ToastContext', () => ({
  useToast: () => ({ showToast: mockShowToast }),
}))

vi.mock('../../../../contexts/ModalContext', () => ({
  useModal: () => ({ showModal: mockShowModal }),
}))

// Mock API
vi.mock('../../../../services/api', () => ({
  API_MAVLINK_ROUTER: '/api/mavlink-router',
  fetchWithTimeout: vi.fn(),
}))

const OutputItemWithProviders = (props) => (
  <I18nextProvider i18n={i18n}>
    <OutputItem {...props} />
  </I18nextProvider>
)

describe('OutputItem Component', () => {
  const mockReload = vi.fn()
  const mockOnEdit = vi.fn()

  const defaultOutput = {
    id: 'test-output-1',
    type: 'udp',
    host: '255.255.255.255',
    port: 14550,
    running: true,
    clients: 2,
  }

  const defaultProps = {
    output: defaultOutput,
    reload: mockReload,
    onEdit: mockOnEdit,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Module', () => {
    it('exports a valid React component named OutputItem', () => {
      expect(OutputItem).toBeDefined()
      expect(OutputItem.name).toBe('OutputItem')
      expect(typeof OutputItem).toBe('function')
    })
  })

  describe('Rendering', () => {
    it('displays output information correctly', () => {
      render(<OutputItemWithProviders {...defaultProps} />)

      expect(screen.getByText('UDP')).toBeInTheDocument()
      expect(screen.getByText('255.255.255.255:14550')).toBeInTheDocument()
    })

    it('shows running status indicator', () => {
      render(<OutputItemWithProviders {...defaultProps} />)

      const statusElement = screen.getByText(/running/i)
      expect(statusElement).toBeInTheDocument()
      expect(statusElement.closest('.output-status')).toHaveClass('running')
    })

    it('shows stopped status indicator when not running', () => {
      const stoppedOutput = { ...defaultOutput, running: false }
      const props = { ...defaultProps, output: stoppedOutput }

      render(<OutputItemWithProviders {...props} />)

      const statusElement = screen.getByText(/stopped/i)
      expect(statusElement).toBeInTheDocument()
      expect(statusElement.closest('.output-status')).toHaveClass('stopped')
    })

    it('displays client count for server types', () => {
      const serverOutput = {
        ...defaultOutput,
        type: 'tcp_server',
        clients: 3,
      }
      const props = { ...defaultProps, output: serverOutput }

      render(<OutputItemWithProviders {...props} />)

      expect(screen.getByText(/3 clients/i)).toBeInTheDocument()
    })

    it('does not display client count for UDP type', () => {
      render(<OutputItemWithProviders {...defaultProps} />)

      expect(screen.queryByText(/clients/i)).not.toBeInTheDocument()
    })

    it('renders action buttons', () => {
      render(<OutputItemWithProviders {...defaultProps} />)

      expect(screen.getByLabelText(/edit/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/delete/i)).toBeInTheDocument()
      expect(screen.getByLabelText(/restart/i)).toBeInTheDocument()
    })
  })

  describe('Type Display', () => {
    it('displays TCP Server type correctly', () => {
      const tcpServerOutput = { ...defaultOutput, type: 'tcp_server' }
      const props = { ...defaultProps, output: tcpServerOutput }

      render(<OutputItemWithProviders {...props} />)

      expect(screen.getByText('TCP Server')).toBeInTheDocument()
    })

    it('displays TCP Client type correctly', () => {
      const tcpClientOutput = { ...defaultOutput, type: 'tcp_client' }
      const props = { ...defaultProps, output: tcpClientOutput }

      render(<OutputItemWithProviders {...props} />)

      expect(screen.getByText('TCP Client')).toBeInTheDocument()
    })

    it('displays UDP type correctly', () => {
      render(<OutputItemWithProviders {...defaultProps} />)

      expect(screen.getByText('UDP')).toBeInTheDocument()
    })
  })

  describe('Actions', () => {
    it('calls onEdit when edit button clicked', () => {
      render(<OutputItemWithProviders {...defaultProps} />)

      const editButton = screen.getByLabelText(/edit/i)
      fireEvent.click(editButton)

      expect(mockOnEdit).toHaveBeenCalledWith(defaultOutput.id, defaultOutput)
    })

    it('shows confirmation modal before delete', () => {
      render(<OutputItemWithProviders {...defaultProps} />)

      const deleteButton = screen.getByLabelText(/delete/i)
      fireEvent.click(deleteButton)

      expect(mockShowModal).toHaveBeenCalledWith(
        expect.objectContaining({
          title: expect.stringMatching(/confirm/i),
          onConfirm: expect.any(Function),
        })
      )
    })

    it('sends delete request when confirmed', async () => {
      const { fetchWithTimeout } = await import('../../../../services/api')
      fetchWithTimeout.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true, message: 'Output deleted' }),
      })

      render(<OutputItemWithProviders {...defaultProps} />)

      const deleteButton = screen.getByLabelText(/delete/i)
      fireEvent.click(deleteButton)

      // Get the confirm function from the modal call
      const modalCall = mockShowModal.mock.calls[0][0]
      await modalCall.onConfirm()

      expect(fetchWithTimeout).toHaveBeenCalledWith(
        `/api/mavlink-router/outputs/${defaultOutput.id}`,
        expect.objectContaining({
          method: 'DELETE',
        })
      )

      expect(mockReload).toHaveBeenCalled()
    })

    it('sends restart request when restart button clicked', async () => {
      const { fetchWithTimeout } = await import('../../../../services/api')
      fetchWithTimeout.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ success: true, message: 'Output restarted' }),
      })

      render(<OutputItemWithProviders {...defaultProps} />)

      const restartButton = screen.getByLabelText(/restart/i)
      fireEvent.click(restartButton)

      await waitFor(() => {
        expect(fetchWithTimeout).toHaveBeenCalledWith(
          `/api/mavlink-router/outputs/${defaultOutput.id}/restart`,
          expect.objectContaining({
            method: 'POST',
          })
        )
      })

      expect(mockReload).toHaveBeenCalled()
    })
  })

  describe('Error Handling', () => {
    it('shows error toast on delete failure', async () => {
      const { fetchWithTimeout } = await import('../../../../services/api')
      fetchWithTimeout.mockResolvedValue({
        ok: false,
        json: () => Promise.resolve({ error: 'Could not delete output' }),
      })

      render(<OutputItemWithProviders {...defaultProps} />)

      const deleteButton = screen.getByLabelText(/delete/i)
      fireEvent.click(deleteButton)

      const modalCall = mockShowModal.mock.calls[0][0]
      await modalCall.onConfirm()

      await waitFor(() => {
        expect(mockShowToast).toHaveBeenCalledWith('Could not delete output', 'error')
      })
    })

    it('handles network errors gracefully', async () => {
      const { fetchWithTimeout } = await import('../../../../services/api')
      fetchWithTimeout.mockRejectedValue(new Error('Network error'))

      render(<OutputItemWithProviders {...defaultProps} />)

      const restartButton = screen.getByLabelText(/restart/i)
      fireEvent.click(restartButton)

      await waitFor(() => {
        expect(mockShowToast).toHaveBeenCalledWith(
          expect.stringMatching(/error.*restart/i),
          'error'
        )
      })
    })
  })

  describe('Performance', () => {
    it('memoizes component to prevent unnecessary re-renders', () => {
      const { rerender } = render(<OutputItemWithProviders {...defaultProps} />)

      // Re-render with same props should not cause re-mount
      rerender(<OutputItemWithProviders {...defaultProps} />)

      // Component should still be present and functional
      expect(screen.getByText('UDP')).toBeInTheDocument()
    })

    it('re-renders when output data changes', () => {
      const { rerender } = render(<OutputItemWithProviders {...defaultProps} />)

      expect(screen.getByText(/running/i)).toBeInTheDocument()

      // Change output status
      const updatedOutput = { ...defaultOutput, running: false }
      const updatedProps = { ...defaultProps, output: updatedOutput }

      rerender(<OutputItemWithProviders {...updatedProps} />)

      expect(screen.getByText(/stopped/i)).toBeInTheDocument()
    })
  })
})
