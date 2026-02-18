import './VPNView.css'
import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../../../contexts/ToastContext'
import { useWebSocket } from '../../../contexts/WebSocketContext'
import api from '../../../services/api'
import VPNStatusCard from './VPNStatusCard'
import VPNPeersList from './VPNPeersList'

/**
 * Copy text to clipboard with fallback for older browsers
 */
const copyToClipboard = async (text) => {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
  } else {
    const input = document.createElement('input')
    input.value = text
    document.body.appendChild(input)
    input.select()
    document.execCommand('copy')
    document.body.removeChild(input)
  }
}

const VPNView = () => {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { messages } = useWebSocket()

  // State
  const [loading, setLoading] = useState(true)
  const [providers, setProviders] = useState([])
  const [selectedProvider, setSelectedProvider] = useState('tailscale')
  const [status, setStatus] = useState(null)
  const [peers, setPeers] = useState([])
  const [loadingPeers, setLoadingPeers] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const [authUrl, setAuthUrl] = useState(null)
  const [authPolling, setAuthPolling] = useState(false)
  const [vpnPreferences, setVpnPreferences] = useState({ auto_connect: false })
  const [_savingPreferences, setSavingPreferences] = useState(false)

  // Refs to avoid stale closures in callbacks
  const authPollingRef = useRef(false)
  const authUrlRef = useRef(null)

  useEffect(() => {
    authPollingRef.current = authPolling
  }, [authPolling])
  useEffect(() => {
    authUrlRef.current = authUrl
  }, [authUrl])

  // --- Data Loading ---

  const loadProviders = useCallback(async () => {
    try {
      const response = await api.get('/api/vpn/providers')
      if (response.ok) {
        const data = await response.json()
        setProviders(data.providers || [])
        const installed = data.providers.find((p) => p.installed)
        if (installed) setSelectedProvider(installed.name)
      }
    } catch (error) {
      console.error('Error loading VPN providers:', error)
    }
  }, [])

  const loadPreferences = useCallback(async () => {
    try {
      const response = await api.get('/api/vpn/preferences')
      if (response.ok) {
        const data = await response.json()
        setVpnPreferences(data.preferences || { auto_connect: false })
      }
    } catch (error) {
      console.error('Error loading VPN preferences:', error)
    }
  }, [])

  const loadStatus = useCallback(async () => {
    try {
      const response = await api.get(`/api/vpn/status?provider=${selectedProvider}`)
      if (response.ok) {
        const data = await response.json()
        setStatus(data)

        // Handle auth state from status response
        if (data.needs_auth && data.auth_url && !authUrlRef.current) {
          setAuthUrl(data.auth_url)
          showToast(t('vpn.authRequired'), 'warning')
        }
        if (data.connected && authPollingRef.current) {
          setAuthPolling(false)
          setAuthUrl(null)
          showToast(t('vpn.connected'), 'success')
        }
        if (data.authenticated && authUrlRef.current) {
          setAuthUrl(null)
          setAuthPolling(false)
        }
        if (!data.connected && !data.authenticated && !data.needs_auth && authUrlRef.current) {
          setAuthUrl(null)
        }
      }
    } catch (error) {
      console.error('Error loading VPN status:', error)
    }
  }, [selectedProvider, showToast, t])

  const loadPeers = useCallback(async () => {
    if (!status?.connected) {
      setPeers([])
      return
    }
    setLoadingPeers(true)
    try {
      const response = await api.get(`/api/vpn/peers?provider=${selectedProvider}`)
      if (response.ok) {
        const data = await response.json()
        setPeers(data.peers || [])
      }
    } catch (error) {
      console.error('Error loading VPN peers:', error)
    }
    setLoadingPeers(false)
  }, [selectedProvider, status?.connected])

  // --- Effects ---

  // Initial data load
  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      await loadProviders()
      await loadPreferences()
      setLoading(false)
    }
    loadData()
  }, [loadProviders, loadPreferences])

  // Refresh status when provider changes
  useEffect(() => {
    if (!loading && selectedProvider) {
      const refreshStatus = async () => {
        try {
          const response = await api.get(`/api/vpn/status?provider=${selectedProvider}`)
          if (response.ok) {
            const data = await response.json()
            setStatus(data)
          }
        } catch (error) {
          console.error('Error refreshing VPN status:', error)
        }
      }
      refreshStatus()
    }
  }, [selectedProvider, loading])

  // WebSocket status updates
  useEffect(() => {
    if (messages.vpn_status) {
      const data = messages.vpn_status
      setStatus(data)

      if (data.needs_auth && data.auth_url && !authUrlRef.current) {
        setAuthUrl(data.auth_url)
        showToast(t('vpn.authRequired'), 'warning')
      }
      if ((data.connected || data.authenticated) && authUrlRef.current) {
        setAuthUrl(null)
        setAuthPolling(false)
      }
    }
  }, [messages.vpn_status, showToast, t])

  // Load peers when connected
  useEffect(() => {
    if (status?.connected && !loading) {
      loadPeers()
      const interval = setInterval(loadPeers, 30000)
      return () => clearInterval(interval)
    } else {
      setPeers([])
    }
  }, [status?.connected, loading, loadPeers])

  // Auth polling effect
  useEffect(() => {
    if (!authPolling) return

    const pollStatus = async () => {
      try {
        const response = await api.get(`/api/vpn/status?provider=${selectedProvider}`)
        if (response.ok) {
          const data = await response.json()
          setStatus(data)
          if (data.authenticated || data.connected) {
            setAuthPolling(false)
            setAuthUrl(null)
            if (data.connected) {
              showToast(t('vpn.connected'), 'success')
            }
          }
        }
      } catch (error) {
        console.error('Error polling VPN status:', error)
      }
    }

    const interval = setInterval(pollStatus, 3000)
    const timeout = setTimeout(() => {
      setAuthPolling(false)
      setAuthUrl(null)
      showToast(t('vpn.authTimeout'), 'warning')
    }, 300000)

    return () => {
      clearInterval(interval)
      clearTimeout(timeout)
    }
  }, [authPolling, selectedProvider, showToast, t])

  // --- Auth URL Helper (consolidates duplicate logic) ---

  const ensureAuthUrl = useCallback(async () => {
    if (authUrl) return authUrl

    const response = await api.post('/api/vpn/connect', { provider: selectedProvider })
    const data = await response.json()

    if (data.needs_auth && data.auth_url) {
      setAuthUrl(data.auth_url)
      return data.auth_url
    }

    if (!response.ok) {
      throw new Error(data.detail || data.error || t('vpn.connectError'))
    }
    if (data.error) {
      throw new Error(data.error)
    }

    throw new Error(t('vpn.connectError'))
  }, [authUrl, selectedProvider, t])

  // --- Action Handlers ---

  const handleConnect = async () => {
    setConnecting(true)
    try {
      const response = await api.post('/api/vpn/connect', { provider: selectedProvider })
      const data = await response.json()

      if (data.needs_auth && data.auth_url) {
        setAuthUrl(data.auth_url)
        showToast(t('vpn.authRequired'), 'info')
      } else if (data.needs_logout) {
        showToast(t('vpn.deviceDeleted'), 'warning')
      } else if (data.already_connected) {
        showToast(t('vpn.alreadyConnected'), 'info')
      } else if (data.success) {
        showToast(t('vpn.connected'), 'success')
        setAuthUrl(null)
        setAuthPolling(false)
        await loadStatus()
      } else if (!response.ok) {
        showToast(data.detail || data.error || t('vpn.connectError'), 'error')
      } else if (data.error) {
        showToast(data.error, 'error')
      }
    } catch (_error) {
      showToast(t('vpn.connectError'), 'error')
    }
    setConnecting(false)
  }

  const handleDisconnect = async () => {
    setConnecting(true)
    try {
      const response = await api.post('/api/vpn/disconnect', { provider: selectedProvider })
      const data = await response.json()
      if (data.success) {
        showToast(t('vpn.disconnected'), 'success')
        setAuthUrl(null)
        setAuthPolling(false)
        await loadStatus()
      }
    } catch (_error) {
      showToast(t('vpn.disconnectError'), 'error')
    }
    setConnecting(false)
  }

  const handleLogout = async () => {
    setConnecting(true)
    try {
      const response = await api.post('/api/vpn/logout', { provider: selectedProvider })
      const data = await response.json()
      if (data.success) {
        showToast(t('vpn.loggedOut'), 'success')
        setAuthUrl(null)
        setAuthPolling(false)
        await loadStatus()
      } else if (data.error?.includes('sudo password')) {
        showToast(t('vpn.logoutNeedsSudo'), 'warning')
      } else if (data.error) {
        showToast(data.error, 'error')
      }
    } catch (_error) {
      showToast(t('vpn.logoutError'), 'error')
    }
    setConnecting(false)
  }

  const openAuthUrl = async () => {
    try {
      setAuthPolling(true)
      const url = await ensureAuthUrl()
      window.open(url, '_blank')
      showToast(t('vpn.pollingStarted'), 'info')
    } catch (error) {
      showToast(error.message, 'error')
      setAuthPolling(false)
    }
  }

  const copyAuthUrl = async () => {
    try {
      if (!authPolling) setAuthPolling(true)
      const url = await ensureAuthUrl()
      await copyToClipboard(url)
      showToast(t('vpn.urlCopied'), 'success')
    } catch (error) {
      showToast(error.message || t('vpn.copyError'), 'error')
      setAuthPolling(false)
    }
  }

  const savePreferences = useCallback(
    async (newPrefs) => {
      setSavingPreferences(true)
      try {
        const response = await api.post('/api/vpn/preferences', newPrefs)
        if (response.ok) {
          const data = await response.json()
          setVpnPreferences(data.preferences || newPrefs)
          showToast(t('vpn.preferencesSaved'), 'success')
        }
      } catch (error) {
        console.error('Error saving VPN preferences:', error)
        showToast(t('vpn.preferencesError'), 'error')
      } finally {
        setSavingPreferences(false)
      }
    },
    [showToast, t]
  )

  const _handleAutoConnectChange = async (enabled) => {
    const newPrefs = { ...vpnPreferences, auto_connect: enabled }
    setVpnPreferences(newPrefs)
    await savePreferences(newPrefs)
  }

  // --- Derived State ---

  const currentProvider = providers.find((p) => p.name === selectedProvider)
  const isInstalled = currentProvider?.installed || false
  const isConnected = status?.connected || false
  const isAuthenticated = status?.authenticated === true

  // --- Render ---

  if (loading) {
    return (
      <div className="card">
        <h2>{t('vpn.title')}</h2>
        <div className="waiting-data">
          <div className="spinner-small"></div>
          {t('common.loadingContent')}
        </div>
      </div>
    )
  }

  return (
    <div className="vpn-view">
      <div className={`vpn-layout ${isConnected ? 'two-column' : ''}`}>
        {/* Left Panel: Status + Auth + Controls + Preferences */}
        <div className="vpn-left-panel">
          <VPNStatusCard
            status={status}
            providers={providers}
            selectedProvider={selectedProvider}
            isConnected={isConnected}
            isInstalled={isInstalled}
            currentProvider={currentProvider}
            onProviderChange={setSelectedProvider}
          />

          {/* Auth Banner */}
          {!isAuthenticated && isInstalled && (
            <div className="card">
              <div className="auth-banner">
                <div className="auth-icon">🔐</div>
                <div className="auth-content">
                  <h3>{t('vpn.authenticationRequired')}</h3>
                  <p>{t('vpn.openAuthUrl')}</p>
                  <div className="auth-actions">
                    <button
                      className="vpn-btn vpn-btn-primary"
                      onClick={openAuthUrl}
                      disabled={connecting}
                    >
                      {t('vpn.openUrl')}
                    </button>
                    <button
                      className="vpn-btn vpn-btn-secondary"
                      onClick={copyAuthUrl}
                      disabled={connecting}
                    >
                      {t('vpn.copyUrl')}
                    </button>
                  </div>
                  {authPolling && (
                    <div className="auth-polling">
                      <div className="spinner-small"></div>
                      <span>{t('vpn.waitingForAuth')}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Controls + Preferences */}
          <div className="card">
            <h2>{t('vpn.controlTitle')}</h2>
            <div className="button-group">
              <button
                className="vpn-btn vpn-btn-primary"
                onClick={handleConnect}
                disabled={!isInstalled || !isAuthenticated || isConnected || connecting}
              >
                {connecting && !isConnected ? '⏳' : '🔗'} {t('vpn.connect')}
              </button>

              <button
                className="vpn-btn vpn-btn-danger"
                onClick={handleDisconnect}
                disabled={!isInstalled || !isConnected || connecting}
              >
                {connecting && isConnected ? '⏳' : '🔌'} {t('vpn.disconnect')}
              </button>

              <button
                className="vpn-btn vpn-btn-warning"
                onClick={handleLogout}
                disabled={!isInstalled || !isAuthenticated || isConnected || connecting}
                title={t('vpn.logoutTooltip')}
              >
                {connecting ? '⏳' : '🚪'} {t('vpn.logout')}
              </button>
            </div>
          </div>
        </div>

        {/* Right Panel: Peers (only when connected) */}
        {isConnected && (
          <div className="vpn-right-panel">
            <VPNPeersList peers={peers} loadingPeers={loadingPeers} onRefresh={loadPeers} />
          </div>
        )}
      </div>
    </div>
  )
}

export default VPNView
