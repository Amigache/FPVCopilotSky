import './VPNView.css'
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../../contexts/ToastContext'
import { useWebSocket } from '../../contexts/WebSocketContext'
import api from '../../services/api'

const VPNView = () => {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { messages } = useWebSocket()
  
  // State
  const [loading, setLoading] = useState(true)
  const [providers, setProviders] = useState([])
  const [selectedProvider, setSelectedProvider] = useState('tailscale')
  const [status, setStatus] = useState(null)
  const [connecting, setConnecting] = useState(false)
  const [authUrl, setAuthUrl] = useState(null)
  const [authPolling, setAuthPolling] = useState(false)

  // Load providers
  const loadProviders = useCallback(async () => {
    try {
      const response = await api.get('/api/vpn/providers')
      if (response.ok) {
        const data = await response.json()
        setProviders(data.providers || [])
        
        // Auto-select first installed provider
        const installed = data.providers.find(p => p.installed)
        if (installed) {
          setSelectedProvider(installed.name)
        }
      }
    } catch (error) {
      console.error('Error loading VPN providers:', error)
    }
  }, [])

  // Load status
  const loadStatus = useCallback(async () => {
    try {
      const response = await api.get(`/api/vpn/status?provider=${selectedProvider}`)
      if (response.ok) {
        const data = await response.json()
        setStatus(data)
        
        // Check if device needs re-authentication (e.g., was deleted from admin panel)
        if (data.needs_auth && data.auth_url && !authUrl) {
          setAuthUrl(data.auth_url)
          showToast(t('vpn.authRequired'), 'warning')
        }
        
        // If connected, stop auth polling and clear auth URL
        if (data.connected && authPolling) {
          setAuthPolling(false)
          setAuthUrl(null)
          showToast(t('vpn.connected'), 'success')
        }
        
        // If not connected and no auth URL, clear it
        if (!data.connected && !data.needs_auth && authUrl) {
          setAuthUrl(null)
        }
      }
    } catch (error) {
      console.error('Error loading VPN status:', error)
    }
  }, [selectedProvider, authPolling, authUrl, showToast, t])

  // Initial load
  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      await loadProviders()
      await loadStatus()
      setLoading(false)
    }
    loadData()
  }, [loadProviders, loadStatus])

  // Refresh status when provider changes
  useEffect(() => {
    if (!loading) {
      loadStatus()
    }
  }, [selectedProvider, loading, loadStatus])

  // Listen for WebSocket updates
  useEffect(() => {
    if (messages.vpn_status) {
      const data = messages.vpn_status
      setStatus(data)
      
      // Check if device needs re-authentication (e.g., deleted from admin panel)
      if (data.needs_auth && data.auth_url && !authUrl) {
        setAuthUrl(data.auth_url)
        showToast(t('vpn.authRequired'), 'warning')
      }
      
      // Clear auth URL if connected
      if (data.connected && authUrl) {
        setAuthUrl(null)
        setAuthPolling(false)
      }
    }
  }, [messages.vpn_status, authUrl, showToast, t])

  // Auth polling effect
  useEffect(() => {
    if (!authPolling) return

    const interval = setInterval(() => {
      loadStatus()
    }, 3000) // Poll every 3 seconds

    // Stop after 5 minutes
    const timeout = setTimeout(() => {
      setAuthPolling(false)
      setAuthUrl(null)
      showToast(t('vpn.authTimeout'), 'warning')
    }, 300000)

    return () => {
      clearInterval(interval)
      clearTimeout(timeout)
    }
  }, [authPolling, loadStatus, showToast, t])

  // Connect to VPN
  const handleConnect = async () => {
    setConnecting(true)
    try {
      const response = await api.post('/api/vpn/connect', {
        provider: selectedProvider
      })
      const data = await response.json()

      if (data.needs_auth && data.auth_url) {
        // Show auth URL but DON'T open automatically or start polling
        setAuthUrl(data.auth_url)
        showToast(t('vpn.authRequired'), 'info')
      } else if (data.needs_logout) {
        // Device was deleted from admin panel
        showToast(t('vpn.deviceDeleted'), 'warning')
      } else if (data.already_connected) {
        showToast(t('vpn.alreadyConnected'), 'info')
      } else if (data.success) {
        showToast(t('vpn.connected'), 'success')
        await loadStatus()
      } else if (data.error) {
        showToast(data.error, 'error')
      }
    } catch (error) {
      showToast(t('vpn.connectError'), 'error')
    }
    setConnecting(false)
  }

  // Disconnect from VPN
  const handleDisconnect = async () => {
    setConnecting(true)
    try {
      const response = await api.post('/api/vpn/disconnect', {
        provider: selectedProvider
      })
      const data = await response.json()

      if (data.success) {
        showToast(t('vpn.disconnected'), 'success')
        await loadStatus()
        setAuthUrl(null)
        setAuthPolling(false)
      }
    } catch (error) {
      showToast(t('vpn.disconnectError'), 'error')
    }
    setConnecting(false)
  }

  // Logout from VPN (clear credentials)
  const handleLogout = async () => {
    setConnecting(true)
    try {
      const response = await api.post('/api/vpn/logout', {
        provider: selectedProvider
      })
      const data = await response.json()

      if (data.success) {
        showToast(t('vpn.loggedOut'), 'success')
        await loadStatus()
        // Clear auth state after logout
        setAuthUrl(null)
        setAuthPolling(false)
      } else if (data.error && data.error.includes('sudo password')) {
        showToast(t('vpn.logoutNeedsSudo'), 'warning')
      } else if (data.error) {
        showToast(data.error, 'error')
      }
    } catch (error) {
      showToast(t('vpn.logoutError'), 'error')
    }
    setConnecting(false)
  }

  // Copy auth URL
  const copyAuthUrl = async () => {
    try {
      // If no auth URL yet, generate it first
      if (!authUrl) {
        const response = await api.post('/api/vpn/connect', {
          provider: selectedProvider
        })
        const data = await response.json()
        if (data.needs_auth && data.auth_url) {
          setAuthUrl(data.auth_url)
          await navigator.clipboard.writeText(data.auth_url)
          showToast(t('vpn.urlCopied'), 'success')
        } else {
          showToast(t('vpn.connectError'), 'error')
        }
      } else {
        await navigator.clipboard.writeText(authUrl)
        showToast(t('vpn.urlCopied'), 'success')
      }
    } catch (error) {
      showToast(t('vpn.copyError'), 'error')
    }
  }

  // Open auth URL and start polling
  const openAuthUrl = async () => {
    try {
      // If no auth URL yet, generate it first
      if (!authUrl) {
        const response = await api.post('/api/vpn/connect', {
          provider: selectedProvider
        })
        const data = await response.json()
        if (data.needs_auth && data.auth_url) {
          setAuthUrl(data.auth_url)
          window.open(data.auth_url, '_blank')
          setAuthPolling(true)
          showToast(t('vpn.pollingStarted'), 'info')
        } else {
          showToast(t('vpn.connectError'), 'error')
        }
      } else {
        // Already have URL, just open it
        window.open(authUrl, '_blank')
        if (!authPolling) {
          setAuthPolling(true)
          showToast(t('vpn.pollingStarted'), 'info')
        }
      }
    } catch (error) {
      showToast(t('vpn.connectError'), 'error')
    }
  }

  if (loading) {
    return (
      <div className="card">
        <h2>{t('vpn.title')}</h2>
        <div className="waiting-data">{t('vpn.loading')}</div>
      </div>
    )
  }

  const currentProvider = providers.find(p => p.name === selectedProvider)
  const isInstalled = currentProvider?.installed || false
  const isConnected = status?.connected || false
  const isAuthenticated = status?.authenticated === true  // Only true when explicitly authenticated

  return (
    <div className="vpn-view">
      {/* Provider Selection */}
      <div className="card">
        <h2>{t('vpn.providerTitle')}</h2>
        
        <div className="form-group">
          <label>{t('vpn.provider')}</label>
          <select 
            value={selectedProvider}
            onChange={(e) => setSelectedProvider(e.target.value)}
            disabled={isConnected}
          >
            {providers.map(provider => (
              <option key={provider.name} value={provider.name}>
                {provider.display_name} {provider.installed ? '✓' : '(not installed)'}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Status Card */}
      <div className="card">
        <h2>{t('vpn.statusTitle')}</h2>

        {!isInstalled ? (
          <div className="warning-box">
            <div className="warning-icon">⚠️</div>
            <div className="warning-content">
              <h3>{t('vpn.notInstalled')}</h3>
              <p>{t('vpn.installInstructions')}</p>
              {currentProvider?.install_url && (
                <a 
                  href={currentProvider.install_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="vpn-btn vpn-btn-link"
                >
                  {t('vpn.downloadProvider')}
                </a>
              )}
            </div>
          </div>
        ) : (
          <div 
            className="vpn-status-container"
            style={{
              border: `1px solid ${isConnected ? 'rgba(76, 175, 80, 0.5)' : 'rgba(102, 102, 102, 0.3)'}`
            }}
          >
            <div className="vpn-status-header">
              <span className="vpn-status-label">{t('vpn.status')}</span>
              <span className={`status-badge ${isConnected ? 'connected' : 'disconnected'}`}>
                {isConnected ? t('vpn.connected') : t('vpn.disconnected')}
              </span>
            </div>
            <div className="vpn-status-grid">
              {status?.ip_address && (
                <div>
                  <div className="vpn-field-label">{t('vpn.ipAddress')}</div>
                  <div className="vpn-field-value">{status.ip_address}</div>
                </div>
              )}

              {status?.hostname && (
                <div>
                  <div className="vpn-field-label">{t('vpn.hostname')}</div>
                  <div className="vpn-field-value">{status.hostname}</div>
                </div>
              )}

              {status?.interface && (
                <div>
                  <div className="vpn-field-label">{t('vpn.interface')}</div>
                  <div className="vpn-field-value">{status.interface}</div>
                </div>
              )}

              {typeof status?.peers_count === 'number' && (
                <div>
                  <div className="vpn-field-label">{t('vpn.peersCount')}</div>
                  <div className="vpn-field-value">
                    {status.online_peers} / {status.peers_count} {t('vpn.online')}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Auth URL Banner - Show when not authenticated */}
        {!isAuthenticated && isInstalled && (
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
        )}

        {/* Auth URL Banner - Show when authenticated but needs re-auth */}
        {authUrl && isAuthenticated && (
          <div className="auth-banner">
            <div className="auth-icon">🔐</div>
            <div className="auth-content">
              <h3>{t('vpn.authenticationRequired')}</h3>
              <p>{t('vpn.openAuthUrl')}</p>
              <div className="auth-actions">
                <button 
                  className="vpn-btn vpn-btn-primary"
                  onClick={openAuthUrl}
                >
                  {t('vpn.openUrl')}
                </button>
                <button 
                  className="vpn-btn vpn-btn-secondary"
                  onClick={copyAuthUrl}
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
        )}
      </div>

      {/* Control Buttons */}
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
  )
}

export default VPNView
