/**
 * ErrorBoundary Tests
 *
 * A throw in a child must render a recoverable fallback, not a blank screen.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import ErrorBoundary from './ErrorBoundary'

function Boom() {
  throw new Error('boom')
}

describe('ErrorBoundary', () => {
  it('renders children when there is no error', () => {
    render(
      <ErrorBoundary>
        <div data-testid="ok">fine</div>
      </ErrorBoundary>
    )
    expect(screen.getByTestId('ok')).toBeInTheDocument()
  })

  it('renders the fallback when a child throws', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>
    )
    expect(screen.getByRole('alert')).toHaveTextContent(/Something went wrong/i)
    spy.mockRestore()
  })
})
