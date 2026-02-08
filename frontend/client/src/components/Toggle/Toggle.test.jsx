/**
 * Tests for Toggle Component
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Toggle from './Toggle'

describe('Toggle Component', () => {
  it('renders without crashing', () => {
    render(<Toggle checked={false} onChange={() => {}} />)
    const toggle = screen.getByRole('checkbox')
    expect(toggle).toBeInTheDocument()
  })

  it('shows label when provided', () => {
    render(<Toggle checked={false} onChange={() => {}} label="Test Label" />)
    expect(screen.getByText('Test Label')).toBeInTheDocument()
  })

  it('calls onChange when clicked', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    
    render(<Toggle checked={false} onChange={onChange} label="Click me" />)
    
    const label = screen.getByLabelText('Click me')
    await user.click(label)
    
    expect(onChange).toHaveBeenCalled()
  })

  it('respects checked prop', () => {
    const { rerender } = render(<Toggle checked={false} onChange={() => {}} />)
    let checkbox = screen.getByRole('checkbox')
    expect(checkbox).not.toBeChecked()

    rerender(<Toggle checked={true} onChange={() => {}} />)
    checkbox = screen.getByRole('checkbox')
    expect(checkbox).toBeChecked()
  })

  it('respects disabled prop', () => {
    render(<Toggle checked={false} onChange={() => {}} disabled={true} />)
    const checkbox = screen.getByRole('checkbox')
    expect(checkbox).toBeDisabled()
  })

  it('applies custom className', () => {
    render(<Toggle checked={false} onChange={() => {}} className="custom-class" />)
    const label = screen.getByRole('checkbox').parentElement
    expect(label).toHaveClass('custom-class')
  })

  it('toggle switch visual state changes', () => {
    const { rerender } = render(<Toggle checked={false} onChange={() => {}} />)
    let switchEl = document.querySelector('.toggle-switch')
    expect(switchEl).toBeInTheDocument()

    rerender(<Toggle checked={true} onChange={() => {}} />)
    switchEl = document.querySelector('.toggle-switch')
    expect(switchEl).toBeInTheDocument()
  })
})
