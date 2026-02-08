/**
 * TabBar Component Tests
 * 
 * Tests for the TabBar component which handles tab navigation
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TabBar from './TabBar'

describe('TabBar Component', () => {
  const mockTabs = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'telemetry', label: 'Telemetry' },
    { id: 'video', label: 'Video' },
    { id: 'network', label: 'Network' },
  ]

  it('renders all tabs', () => {
    const mockOnChange = vi.fn()
    render(<TabBar tabs={mockTabs} activeTab="dashboard" onTabChange={mockOnChange} />)

    expect(screen.getByRole('button', { name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Telemetry' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Video' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Network' })).toBeInTheDocument()
  })

  it('highlights the active tab', () => {
    const mockOnChange = vi.fn()
    render(<TabBar tabs={mockTabs} activeTab="video" onTabChange={mockOnChange} />)

    const videoTab = screen.getByRole('button', { name: 'Video' })
    expect(videoTab).toHaveClass('active')
  })

  it('calls onTabChange when tab is clicked', async () => {
    const mockOnChange = vi.fn()
    const user = userEvent.setup()
    render(<TabBar tabs={mockTabs} activeTab="dashboard" onTabChange={mockOnChange} />)

    const networkTab = screen.getByRole('button', { name: 'Network' })
    await user.click(networkTab)

    expect(mockOnChange).toHaveBeenCalledWith('network')
  })

  it('handles multiple tab clicks', async () => {
    const mockOnChange = vi.fn()
    const user = userEvent.setup()
    render(<TabBar tabs={mockTabs} activeTab="dashboard" onTabChange={mockOnChange} />)

    await user.click(screen.getByRole('button', { name: 'Video' }))
    expect(mockOnChange).toHaveBeenCalledWith('video')

    await user.click(screen.getByRole('button', { name: 'Network' }))
    expect(mockOnChange).toHaveBeenCalledWith('network')

    expect(mockOnChange).toHaveBeenCalledTimes(2)
  })

  it('renders single tab correctly', () => {
    const mockOnChange = vi.fn()
    const singleTab = [{ id: 'dashboard', label: 'Dashboard' }]
    render(<TabBar tabs={singleTab} activeTab="dashboard" onTabChange={mockOnChange} />)

    expect(screen.getByRole('button', { name: 'Dashboard' })).toHaveClass('active')
  })

  it('handles empty tabs array', () => {
    const mockOnChange = vi.fn()
    const { container } = render(<TabBar tabs={[]} activeTab="" onTabChange={mockOnChange} />)

    expect(container.querySelectorAll('.tab-button')).toHaveLength(0)
  })

  it('updates active tab when activeTab prop changes', () => {
    const mockOnChange = vi.fn()
    const { rerender } = render(<TabBar tabs={mockTabs} activeTab="dashboard" onTabChange={mockOnChange} />)

    let dashboardTab = screen.getByRole('button', { name: 'Dashboard' })
    expect(dashboardTab).toHaveClass('active')

    rerender(<TabBar tabs={mockTabs} activeTab="telemetry" onTabChange={mockOnChange} />)

    dashboardTab = screen.getByRole('button', { name: 'Dashboard' })
    expect(dashboardTab).not.toHaveClass('active')

    const telemetryTab = screen.getByRole('button', { name: 'Telemetry' })
    expect(telemetryTab).toHaveClass('active')
  })
})
