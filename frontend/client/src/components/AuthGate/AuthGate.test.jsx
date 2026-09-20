import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'

const { mockAuth } = vi.hoisted(() => ({ mockAuth: {} }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, fallback) => fallback || key, i18n: { language: 'en' } }),
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth,
}))

import AuthGate from './AuthGate'

describe('AuthGate', () => {
  beforeEach(() => {
    for (const key of Object.keys(mockAuth)) delete mockAuth[key]
    Object.assign(mockAuth, {
      loading: false,
      authRequired: false,
      authenticated: true,
      login: vi.fn(),
    })
  })

  it('renders children when auth is disabled', () => {
    render(
      <AuthGate>
        <div>APP</div>
      </AuthGate>
    )
    expect(screen.getByText('APP')).toBeInTheDocument()
  })

  it('renders children when authenticated', () => {
    mockAuth.authRequired = true
    mockAuth.authenticated = true
    render(
      <AuthGate>
        <div>APP</div>
      </AuthGate>
    )
    expect(screen.getByText('APP')).toBeInTheDocument()
  })

  it('shows the token form when auth is required', () => {
    mockAuth.authRequired = true
    mockAuth.authenticated = false
    render(
      <AuthGate>
        <div>APP</div>
      </AuthGate>
    )
    expect(screen.queryByText('APP')).not.toBeInTheDocument()
    expect(screen.getByLabelText('API token')).toBeInTheDocument()
  })

  it('submits the entered token and surfaces an error when invalid', async () => {
    mockAuth.authRequired = true
    mockAuth.authenticated = false
    mockAuth.login = vi.fn().mockResolvedValue(false)
    render(
      <AuthGate>
        <div>APP</div>
      </AuthGate>
    )

    fireEvent.change(screen.getByLabelText('API token'), { target: { value: 'abc' } })
    fireEvent.click(screen.getByRole('button', { name: 'Unlock' }))

    await waitFor(() => expect(mockAuth.login).toHaveBeenCalledWith('abc'))
    expect(await screen.findByText('Invalid token')).toBeInTheDocument()
  })

  it('shows a loading state while the auth status is unknown', () => {
    mockAuth.loading = true
    render(
      <AuthGate>
        <div>APP</div>
      </AuthGate>
    )
    expect(screen.queryByText('APP')).not.toBeInTheDocument()
  })
})
