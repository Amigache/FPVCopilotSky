import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { fetchWithTimeout, getAuthToken, setAuthToken, clearAuthToken } from '../services/api'

const AuthContext = createContext(null)

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}

/**
 * Opt-in authentication provider.
 *
 * On mount it asks the backend whether auth is required (`/api/auth/status`,
 * always public) and whether the currently stored token is valid. If the
 * backend does not enforce auth, the app loads normally.
 */
export const AuthProvider = ({ children }) => {
  const [loading, setLoading] = useState(true)
  const [authRequired, setAuthRequired] = useState(false)
  const [authenticated, setAuthenticated] = useState(true)
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await fetchWithTimeout('/api/auth/status')
      const data = await response.json()
      const required = !!data.auth_required
      setAuthRequired(required)
      setAuthenticated(required ? !!data.authenticated : true)
    } catch (err) {
      // If the status endpoint cannot be reached, do not lock the user out.
      setAuthRequired(false)
      setAuthenticated(true)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const login = useCallback(async (token) => {
    setAuthToken(token)
    const response = await fetchWithTimeout('/api/auth/status')
    const data = await response.json()
    if (data.auth_required && !data.authenticated) {
      clearAuthToken()
      setAuthRequired(true)
      setAuthenticated(false)
      return false
    }
    setAuthRequired(!!data.auth_required)
    setAuthenticated(true)
    return true
  }, [])

  const logout = useCallback(() => {
    clearAuthToken()
    setAuthenticated(false)
  }, [])

  const value = {
    loading,
    authRequired,
    authenticated,
    error,
    login,
    logout,
    refresh,
    hasStoredToken: !!getAuthToken(),
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
