import './VPNView.css'
import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../../contexts/ToastContext'
import { useWebSocket } from '../../contexts/WebSocketContext'
import api from '../../services/api'

// Helper function to format bytes
const formatBytes = (bytes) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i]
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
  
  // Refs to avoid infinite loops
  const authPollingRef = useRef(false)
  const authUrlRef = useRef(null)
  const statusRef = useRef(null)

  // Update refs when state changes
  useEffect(() => { authPollingRef.current = authPolling }, [authPolling])
  useEffect(() => { authUrlRef.current = authUrl }, [authUrl])
  useEffect(() => { statusRef.current = status }, [status])

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
        if (data.needs_auth && data.auth_url && !authUrlRef.current) {
          setAuthUrl(data.auth_url)
          showToast(t('vpn.authRequired'), 'warning')
        }
        
        // If connected, stop auth polling and clear auth URL
        if (data.connected && authPollingRef.current) {
          setAuthPolling(false)
          setAuthUrl(null)
          showToast(t('vpn.connected'), 'success')
        }
        
        // If authenticated, clear auth URL regardless of connection status
        if (data.authenticated && authUrlRef.current) {
          setAuthUrl(null)
          setAuthPolling(false)
        }
        
        // If not connected and not authenticated and no auth URL, ensure it stays null
        if (!data.connected && !data.authenticated && !data.needs_auth && authUrlRef.current) {
          setAuthUrl(null)
        }
      }
    } catch (error) {
      console.error('Error loading VPN status:', error)
    }
  }, [selectedProvider, showToast, t])

  // Load peers
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

  // Initial load
  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      await loadProviders()
      await loadStatus()
      setLoading(false)
    }
    loadData()
  }, [loadProviders, selectedProvider])

  // Refresh status when provider changes (without dependency on loadStatus)
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

  // Listen for WebSocket updates
  useEffect(() => {
    if (messages.vpn_status) {
      const data = messages.vpn_status
      setStatus(data)
      
      // Check if device needs re-authentication (e.g., deleted from admin panel)
      if (data.needs_auth && data.auth_url && !authUrlRef.current) {
        setAuthUrl(data.auth_url)
        showToast(t('vpn.authRequired'), 'warning')
      }
      
      // Clear auth URL if connected or authenticated
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
      // Refresh peers every 30 seconds when connected
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
          
          // If authenticated or connected, stop polling
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

    const interval = setInterval(pollStatus, 3000) // Poll every 3 seconds

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
  }, [authPolling, selectedProvider, showToast, t])

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
        setAuthUrl(null)
        setAuthPolling(false)
        await loadStatus()
      } else if (!response.ok) {
        // HTTP error response (400, 500)
        showToast(data.detail || data.error || t('vpn.connectError'), 'error')
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
        setAuthUrl(null)
        setAuthPolling(false)
        // Load status after cleaning auth state
        await loadStatus()
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
        // Clear auth state after logout - this will trigger the banner to show
        setAuthUrl(null)
        setAuthPolling(false)
        await loadStatus()
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
        // Start polling immediately so user sees feedback while URL is being fetched
        setAuthPolling(true)
        const response = await api.post('/api/vpn/connect', {
          provider: selectedProvider
        })
        const data = await response.json()
        if (data.needs_auth && data.auth_url) {
          setAuthUrl(data.auth_url)
          await navigator.clipboard.writeText(data.auth_url)
          showToast(t('vpn.urlCopied'), 'success')
        } else if (!response.ok) {
          const errorMsg = data.detail || data.error || t('vpn.connectError')
          console.error('copyAuthUrl - HTTP error:', response.status, errorMsg)
          showToast(errorMsg, 'error')
          setAuthPolling(false)
        } else if (data.error) {
          console.error('copyAuthUrl - API error:', data.error)
          showToast(data.error, 'error')
          setAuthPolling(false)
        } else {
          console.error('copyAuthUrl - Unexpected response:', data)
          showToast(t('vpn.connectError'), 'error')
          setAuthPolling(false)
        }
      } else {
        await navigator.clipboard.writeText(authUrl)
        showToast(t('vpn.urlCopied'), 'success')
        if (!authPolling) {
          setAuthPolling(true)
        }
      }
    } catch (error) {
      console.error('copyAuthUrl - Exception:', error)
      showToast(t('vpn.copyError'), 'error')
      setAuthPolling(false)
    }
  }

  // Open auth URL and start polling
  const openAuthUrl = async () => {
    try {
      // If no auth URL yet, generate it first
      if (!authUrl) {
        // Start polling immediately so user sees feedback while URL is being fetched
        setAuthPolling(true)
        const response = await api.post('/api/vpn/connect', {
          provider: selectedProvider
        })
        const data = await response.json()
        if (data.needs_auth && data.auth_url) {
          setAuthUrl(data.auth_url)
          window.open(data.auth_url, '_blank')
          showToast(t('vpn.pollingStarted'), 'info')
        } else if (!response.ok) {
          // HTTP error (400, 500, etc) - detail field from HTTPException
          const errorMsg = data.detail || data.error || t('vpn.connectError')
          console.error('openAuthUrl - HTTP error:', response.status, errorMsg)
          showToast(errorMsg, 'error')
          setAuthPolling(false)
        } else if (data.error) {
          console.error('openAuthUrl - API error:', data.error)
          showToast(data.error, 'error')
          setAuthPolling(false)
        } else {
          console.error('openAuthUrl - Unexpected response:', data)
          showToast(t('vpn.connectError'), 'error')
          setAuthPolling(false)
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
      console.error('openAuthUrl - Exception:', error)
      showToast(t('vpn.connectError'), 'error')
    }
  }

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
      </div>

      {/* Peers/Nodes Card */}
      {isConnected && (
        <div className="card">
          <div className="card-header">
            <h2>🌐 {t('vpn.peersTitle')}</h2>
            <button 
              className="vpn-btn-refresh" 
              onClick={loadPeers} 
              disabled={loadingPeers}
            >
              {loadingPeers ? '⏳' : '🔄'}
            </button>
          </div>

          {loadingPeers && peers.length === 0 ? (
            <div className="waiting-data">
              <div className="spinner-small"></div>
              {t('vpn.loadingPeers')}
            </div>
          ) : (
            <div className="peers-list">
              {peers.map((peer) => (
                <div 
                  key={peer.id} 
                  className={`peer-item ${peer.is_self ? 'peer-self' : ''} ${peer.online ? 'peer-online' : 'peer-offline'}`}
                >
                  <div className="peer-header">
                    <div className="peer-name">
                      {peer.is_self && '⭐ '}
                      {peer.hostname}
                    </div>
                    <div className={`peer-status ${peer.online ? 'status-online' : 'status-offline'}`}>
                      {peer.online ? '● Online' : '○ Offline'}
                    </div>
                  </div>
                  <div className="peer-details">
                    <div className="peer-detail">
                      <span className="peer-detail-label">IP:</span>
                      <span className="peer-detail-value">{peer.ip_addresses[0] || 'N/A'}</span>
                    </div>
                    <div className="peer-detail">
                      <span className="peer-detail-label">OS:</span>
                      <span className="peer-detail-value">{peer.os}</span>
                    </div>
                    {!peer.is_self && peer.rx_bytes !== undefined && (
                      <>
                        <div className="peer-detail">
                          <span className="peer-detail-label">↓ RX:</span>
                          <span className="peer-detail-value">{formatBytes(peer.rx_bytes)}</span>
                        </div>
                        <div className="peer-detail">
                          <span className="peer-detail-label">↑ TX:</span>
                          <span className="peer-detail-value">{formatBytes(peer.tx_bytes)}</span>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              ))}
              {peers.length === 0 && !loadingPeers && (
                <div className="no-peers">
                  {t('vpn.noPeers')}
                </div>
              )}
            </div>
          )}
        </div>
      )}

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
