/**
 * Badge Component Tests
 *
 * Tests for the Badge component which displays status indicators
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import Badge from './Badge'

describe('Badge Component', () => {
  it('renders badge with default success variant', () => {
    render(<Badge>Online</Badge>)
    const badge = screen.getByText('Online')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveClass('badge', 'badge-success')
  })

  it('renders badge with custom variant', () => {
    render(<Badge variant="danger">Offline</Badge>)
    const badge = screen.getByText('Offline')
    expect(badge).toHaveClass('badge', 'badge-danger')
  })

  it('renders badge with warning variant', () => {
    render(<Badge variant="warning">Warning</Badge>)
    const badge = screen.getByText('Warning')
    expect(badge).toHaveClass('badge', 'badge-warning')
  })

  it('renders badge with info variant', () => {
    render(<Badge variant="info">Info</Badge>)
    const badge = screen.getByText('Info')
    expect(badge).toHaveClass('badge', 'badge-info')
  })

  it('renders children content', () => {
    render(<Badge>Custom Content</Badge>)
    expect(screen.getByText('Custom Content')).toBeInTheDocument()
  })

  it('renders multiple children', () => {
    render(
      <Badge>
        Status: <span>Active</span>
      </Badge>
    )
    expect(screen.getByText('Status:')).toBeInTheDocument()
    expect(screen.getByText('Active')).toBeInTheDocument()
  })

  it('renders with default success variant when not specified', () => {
    const { container } = render(<Badge>Test</Badge>)
    const badge = container.querySelector('.badge-success')
    expect(badge).toBeInTheDocument()
  })
})
