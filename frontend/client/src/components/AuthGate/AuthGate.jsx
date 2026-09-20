import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../../contexts/AuthContext'
import './AuthGate.css'

/**
 * Blocks the application until the user provides a valid API token.
 *
 * When the backend has authentication disabled (`FPV_API_TOKEN` unset) this
 * component is transparent and renders its children immediately.
 */
const AuthGate = ({ children }) => {
  const { t } = useTranslation()
  const { loading, authRequired, authenticated, login } = useAuth()
  const [token, setToken] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  if (loading) {
    return (
      <div className="auth-gate" role="status" aria-live="polite">
        <div className="auth-gate__loading">{t('common.loading', 'Loading…')}</div>
      </div>
    )
  }

  if (!authRequired || authenticated) {
    return children
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const value = token.trim()
    if (!value) return
    setSubmitting(true)
    setError('')
    try {
      const ok = await login(value)
      if (!ok) setError(t('auth.invalidToken', 'Invalid token'))
    } catch (err) {
      setError(err.message || t('auth.error', 'Authentication error'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="auth-gate"
      role="dialog"
      aria-modal="true"
      aria-label={t('auth.title', 'Authentication required')}
    >
      <form className="auth-gate__card" onSubmit={handleSubmit}>
        <div className="auth-gate__icon" aria-hidden="true">
          🔒
        </div>
        <h1>{t('auth.title', 'Authentication required')}</h1>
        <p className="auth-gate__help">
          {t('auth.help', 'Enter the API token (FPV_API_TOKEN) configured on the device.')}
        </p>
        <label className="auth-gate__label" htmlFor="auth-token">
          {t('auth.tokenLabel', 'API token')}
        </label>
        <input
          id="auth-token"
          type="password"
          autoComplete="current-password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          disabled={submitting}
          autoFocus
        />
        {error ? (
          <div className="auth-gate__error" role="alert">
            {error}
          </div>
        ) : null}
        <button type="submit" disabled={submitting || !token.trim()}>
          {submitting ? t('auth.submitting', 'Verifying…') : t('auth.submit', 'Unlock')}
        </button>
      </form>
    </div>
  )
}

export default AuthGate
