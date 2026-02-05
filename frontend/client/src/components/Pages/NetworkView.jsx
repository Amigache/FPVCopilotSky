import './NetworkView.css'
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../../contexts/ToastContext'
import { useModal } from '../../contexts/ModalContext'
import { useWebSocket } from '../../contexts/WebSocketContext'
import api from '../../services/api'

const NetworkView = () => {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { showModal } = useModal()
  const { messages } = useWebSocket()
  
  // State
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [status, setStatus] = useState(null)
  const [hilinkStatus, setHilinkStatus] = useState(null)
  const [wifiNetworks, setWifiNetworks] = useState([])
  const [wifiScanning, setWifiScanning] = useState(false)
  const [changingMode, setChangingMode] = useState(false)
  const [changingNetworkMode, setChangingNetworkMode] = useState(false)
  const [modemRebooting, setModemRebooting] = useState(false)
  
  // WiFi Connect Modal
  const [connectModal, setConnectModal] = useState({ open: false, ssid: '', security: '' })
  const [wifiPassword, setWifiPassword] = useState('')
  const [connecting, setConnecting] = useState(false)

  // Load network status
  const loadStatus = useCallback(async () => {
    try {
      const response = await api.get('/api/network/status')
      if (response.ok) {
        const data = await response.json()
        setStatus(data)
      }
    } catch (error) {
      console.error('Error loading network status:', error)
    }
  }, [])

  // Load HiLink modem status (with shorter timeout since modem should respond quickly)
  const loadHilinkStatus = useCallback(async () => {
    try {
      const response = await api.get('/api/network/hilink/status', 10000) // 10s timeout
      if (response.ok) {
        const data = await response.json()
        setHilinkStatus(data)
      } else {
        // Modem not responding - set as disconnected (no error log needed)
        setHilinkStatus({ available: false, connected: false, error: 'No response from modem' })
      }
    } catch (error) {
      // Timeout or network error - modem is likely disconnected
      // This is expected when modem is not connected, no need to log
      setHilinkStatus({ available: false, connected: false, error: error.message || 'Connection error' })
    }
  }, [])

  // Load WiFi networks
  const loadWifiNetworks = useCallback(async () => {
    setWifiScanning(true)
    try {
      const response = await api.get('/api/network/wifi/networks')
      if (response.ok) {
        const data = await response.json()
        setWifiNetworks(data.networks || [])
      }
    } catch (error) {
      console.error('Error loading WiFi networks:', error)
    }
    setWifiScanning(false)
  }, [])

  // Initial load
  useEffect(() => {
    const loadAll = async () => {
      setLoading(true)
      await loadStatus()
      await loadHilinkStatus()
      await loadWifiNetworks()
      setLoading(false)
    }
    loadAll()
  }, [loadStatus, loadHilinkStatus, loadWifiNetworks])

  // Update from WebSocket - network status
  useEffect(() => {
    if (messages.network_status) {
      setStatus(messages.network_status)
      setLoading(false)
    }
  }, [messages.network_status])

  // Refresh all
  const handleRefresh = async () => {
    setRefreshing(true)
    await loadStatus()
    await loadHilinkStatus()
    await loadWifiNetworks()
    setRefreshing(false)
    showToast(t('network.refreshed', 'Status updated'), 'success')
  }

  // Set priority mode
  const handleSetMode = async (mode) => {
    setChangingMode(true)
    try {
      const response = await api.post('/api/network/priority', { mode })
      if (response.ok) {
        await loadStatus()
        showToast(
          mode === 'wifi' 
            ? t('network.wifiPrimarySet', 'WiFi set as primary') 
            : t('network.modemPrimarySet', '4G set as primary'),
          'success'
        )
      } else {
        const data = await response.json()
        showToast(data.detail || t('network.modeError', 'Error changing mode'), 'error')
      }
    } catch (error) {
      showToast(error.message || t('network.modeError', 'Error changing mode'), 'error')
    }
    setChangingMode(false)
  }

  // Set modem network mode (2G/3G/4G/Auto)
  const handleSetNetworkMode = async (mode) => {
    setChangingNetworkMode(true)
    try {
      const response = await api.post('/api/network/hilink/mode', { mode })
      if (response.ok) {
        showToast(t('network.networkModeSet', 'Network mode changed'), 'success')
        await loadHilinkStatus()
      } else {
        const data = await response.json()
        showToast(data.detail || t('network.networkModeError', 'Error changing network mode'), 'error')
      }
    } catch (error) {
      showToast(error.message, 'error')
    }
    setChangingNetworkMode(false)
  }

  // Reboot modem
  const handleRebootModem = () => {
    showModal({
      title: t('network.rebootModem', 'Reboot Modem'),
      message: t('network.confirmReboot', 'Are you sure you want to reboot the 4G modem? Connection will be lost temporarily.'),
      type: 'confirm',
      confirmText: t('network.reboot', 'Reboot'),
      cancelText: t('common.cancel', 'Cancel'),
      onConfirm: async () => {
        try {
          const response = await api.post('/api/network/hilink/reboot')
          if (response.ok) {
            setModemRebooting(true)
            showToast(t('network.modemRebooting', 'Modem is rebooting...'), 'success')
            
            // Poll for modem to come back online (check every 5s for up to 60s)
            let attempts = 0
            const maxAttempts = 12
            const checkModem = async () => {
              attempts++
              try {
                const checkResponse = await api.get('/api/network/hilink/status', 5000) // 5s timeout for reboot check
                if (checkResponse.ok) {
                  const data = await checkResponse.json()
                  if (data.available) {
                    setModemRebooting(false)
                    showToast(t('network.modemReady', 'Modem is back online'), 'success')
                    await loadHilinkStatus()
                    return
                  }
                }
              } catch (e) {
                // Expected during reboot
              }
              
              if (attempts < maxAttempts) {
                setTimeout(checkModem, 5000)
              } else {
                setModemRebooting(false)
                showToast(t('network.modemTimeout', 'Modem did not respond. Check connection.'), 'warning')
              }
            }
            
            // Start checking after initial delay
            setTimeout(checkModem, 10000)
          } else {
            const data = await response.json()
            showToast(data.detail || 'Error', 'error')
          }
        } catch (error) {
          showToast(error.message, 'error')
        }
      }
    })
  }

  // Open WiFi connect modal
  const handleWifiClick = (network) => {
    if (network.connected) return
    setConnectModal({ open: true, ssid: network.ssid, security: network.security })
    setWifiPassword('')
  }

  // Connect to WiFi
  const handleWifiConnect = async () => {
    setConnecting(true)
    try {
      const payload = { ssid: connectModal.ssid }
      if (wifiPassword) {
        payload.password = wifiPassword
      }
      
      const response = await api.post('/api/network/wifi/connect', payload)
      if (response.ok) {
        showToast(t('network.wifiConnected', 'Connected to {{ssid}}', { ssid: connectModal.ssid }), 'success')
        setConnectModal({ open: false, ssid: '', security: '' })
        await loadStatus()
        await loadWifiNetworks()
      } else {
        const data = await response.json()
        showToast(data.detail || t('network.wifiConnectError', 'Connection failed'), 'error')
      }
    } catch (error) {
      showToast(error.message || t('network.wifiConnectError', 'Connection failed'), 'error')
    }
    setConnecting(false)
  }

  // Disconnect WiFi
  const handleWifiDisconnect = async () => {
    try {
      const response = await api.post('/api/network/wifi/disconnect')
      if (response.ok) {
        showToast(t('network.wifiDisconnected', 'Disconnected from WiFi'), 'success')
        await loadStatus()
        await loadWifiNetworks()
      }
    } catch (error) {
      showToast(error.message, 'error')
    }
  }

  // Get signal strength category
  const getSignalCategory = (signal) => {
    if (signal >= 75) return 'excellent'
    if (signal >= 50) return 'good'
    if (signal >= 25) return 'fair'
    return 'poor'
  }

  // Get signal bars count
  const getSignalBars = (signal) => {
    if (signal >= 75) return 4
    if (signal >= 50) return 3
    if (signal >= 25) return 2
    return 1
  }

  if (loading) {
    return (
      <div className="card">
        <h2>🌐 {t('network.title', 'Network')}</h2>
        <div className="waiting-data">
          {t('network.loading', 'Loading network status...')}
        </div>
      </div>
    )
  }

  const currentMode = status?.mode || 'unknown'
  const modem = status?.modem || {}
  const interfaces = status?.interfaces || []
  const routes = status?.routes || []

  return (
    <div className="network-view">
      {/* Mode Banner */}
      <div className={`network-mode-banner ${currentMode === 'modem' ? 'modem-primary' : 'wifi-primary'}`}>
        <div className="mode-info">
          <span className="mode-icon">{currentMode === 'modem' ? '📶' : '📡'}</span>
          <div className="mode-text">
            <span className="mode-title">
              {currentMode === 'modem' 
                ? t('network.modemPrimary', '4G Primary Mode') 
                : t('network.wifiPrimary', 'WiFi Primary Mode')}
            </span>
            <span className="mode-description">
              {currentMode === 'modem' 
                ? t('network.modemPrimaryDesc', 'Using 4G modem as main connection')
                : t('network.wifiPrimaryDesc', 'Using WiFi as main connection')}
            </span>
          </div>
        </div>
        <div className="mode-toggle">
          <button 
            className={`mode-btn ${currentMode === 'wifi' ? 'active' : ''}`}
            onClick={() => handleSetMode('wifi')}
            disabled={changingMode || currentMode === 'wifi'}
          >
            📡 WiFi
          </button>
          <button 
            className={`mode-btn ${currentMode === 'modem' ? 'active' : ''}`}
            onClick={() => handleSetMode('modem')}
            disabled={changingMode || currentMode === 'modem' || !modem.detected}
          >
            📶 4G
          </button>
        </div>
      </div>

      <div className="network-columns">
        {/* Left Column */}
        <div className="network-col">
          {/* Interfaces Card */}
          <div className="card">
            <div className="card-header">
              <h2>🔌 {t('network.interfaces', 'Interfaces')}</h2>
              <button 
                className="btn-refresh" 
                onClick={handleRefresh} 
                disabled={refreshing}
              >
                {refreshing ? '...' : '🔄'}
              </button>
            </div>
            <div className="interfaces-list">
              {interfaces.map((iface) => (
                <div 
                  key={iface.name} 
                  className={`interface-item ${iface.state}`}
                >
                  <div className="interface-info">
                    <span className="interface-name">
                      {iface.type === 'wifi' && '📡 '}
                      {iface.type === 'modem' && '📶 '}
                      {iface.type === 'ethernet' && '🔌 '}
                      {iface.name}
                      {iface.connection && ` (${iface.connection})`}
                    </span>
                    <span className="interface-details">
                      {iface.ip_address && <span>IP: {iface.ip_address}</span>}
                      {iface.gateway && <span>GW: {iface.gateway}</span>}
                      {iface.speed && <span>{iface.speed}</span>}
                    </span>
                  </div>
                  {iface.metric !== null && iface.metric !== undefined && (
                    <span className={`interface-metric ${iface.metric <= 100 ? 'primary' : ''}`}>
                      Metric: {iface.metric}
                    </span>
                  )}
                </div>
              ))}
              {interfaces.length === 0 && (
                <div className="loading-indicator">
                  {t('network.noInterfaces', 'No interfaces found')}
                </div>
              )}
            </div>
          </div>

          {/* Routes Card */}
          <div className="card">
            <h2>🛤️ {t('network.routes', 'Default Routes')}</h2>
            {routes.length > 0 ? (
              <table className="routes-table">
                <thead>
                  <tr>
                    <th>{t('network.interface', 'Interface')}</th>
                    <th>{t('network.gateway', 'Gateway')}</th>
                    <th>{t('network.metric', 'Metric')}</th>
                  </tr>
                </thead>
                <tbody>
                  {routes.map((route, idx) => (
                    <tr key={idx}>
                      <td className={idx === 0 ? 'primary-route' : ''}>
                        {route.interface}
                      </td>
                      <td>{route.gateway}</td>
                      <td className={idx === 0 ? 'primary-route' : ''}>
                        {route.metric || '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="loading-indicator">
                {t('network.noRoutes', 'No default routes')}
              </div>
            )}
          </div>
        </div>

        {/* Right Column */}
        <div className="network-col">
          {/* WiFi Networks Card */}
          <div className="card">
            <div className="card-header">
              <h2>📡 {t('network.wifiNetworks', 'WiFi Networks')}</h2>
              <button 
                className="btn-refresh" 
                onClick={loadWifiNetworks} 
                disabled={wifiScanning}
              >
                {wifiScanning ? '...' : '🔍'}
              </button>
            </div>
            
            {wifiScanning ? (
              <div className="loading-indicator">
                <div className="spinner"></div>
                {t('network.scanning', 'Scanning...')}
              </div>
            ) : (
              <div className="wifi-networks">
                {wifiNetworks.map((network) => (
                  <div 
                    key={network.ssid}
                    className={`wifi-network ${network.connected ? 'connected' : ''}`}
                    onClick={() => handleWifiClick(network)}
                  >
                    <div className="wifi-info">
                      <div className="wifi-signal">
                        <div className="signal-bars">
                          {[1, 2, 3, 4].map((bar) => (
                            <div 
                              key={bar}
                              className={`signal-bar ${bar <= getSignalBars(network.signal) ? 'active' : ''}`}
                            />
                          ))}
                        </div>
                      </div>
                      <div>
                        <div className="wifi-ssid">{network.ssid}</div>
                        <div className="wifi-security">{network.security || 'Open'}</div>
                      </div>
                    </div>
                    {network.connected ? (
                      <span className="wifi-connected-badge" onClick={handleWifiDisconnect}>
                        ✓ {t('network.connected', 'Connected')}
                      </span>
                    ) : null}
                  </div>
                ))}
                {wifiNetworks.length === 0 && (
                  <div className="loading-indicator">
                    {t('network.noNetworks', 'No WiFi networks found')}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Modem Card - Enhanced with HiLink API */}
          <div className="card modem-card">
            {modemRebooting && (
              <div className="modem-rebooting-overlay">
                <div className="spinner-large" />
                <div className="rebooting-text">
                  {t('network.modemRebooting', 'Modem is rebooting...')}
                </div>
                <div className="rebooting-hint">
                  {t('network.pleaseWait', 'Please wait...')}
                </div>
              </div>
            )}
            <div className="card-header">
              <h2>📶 {t('network.modem', '4G USB Modem')}</h2>
              {hilinkStatus?.available && !modemRebooting && (
                <button 
                  className="btn-refresh" 
                  onClick={loadHilinkStatus}
                  title={t('network.refresh', 'Refresh')}
                >
                  🔄
                </button>
              )}
            </div>
            <div className="modem-status">
              {hilinkStatus?.available ? (
                <>
                  {/* Device Info */}
                  <div className="modem-device-info">
                    <span className="modem-device-name">
                      {hilinkStatus.device?.device_name || 'USB Modem'}
                    </span>
                    <span className="modem-network-type">
                      {hilinkStatus.network?.network_type || 'Unknown'}
                    </span>
                  </div>

                  {/* Signal Strength */}
                  <div className="modem-signal-section">
                    <div className="signal-bars-large">
                      {[1, 2, 3, 4, 5].map((bar) => (
                        <div 
                          key={bar}
                          className={`signal-bar-large ${bar <= (hilinkStatus.network?.signal_icon || 0) ? 'active' : ''}`}
                        />
                      ))}
                    </div>
                    <div className="signal-details">
                      <span className="signal-percent">
                        {hilinkStatus.signal?.signal_percent || 0}%
                      </span>
                      <span className="signal-rssi">
                        {hilinkStatus.signal?.rssi || '-'}
                      </span>
                    </div>
                  </div>

                  {/* Traffic Stats */}
                  <div className="modem-traffic">
                    <div className="traffic-stat">
                      <span className="traffic-icon">↓</span>
                      <span className="traffic-value">{hilinkStatus.traffic?.current_download || '0 B'}</span>
                    </div>
                    <div className="traffic-stat">
                      <span className="traffic-icon">↑</span>
                      <span className="traffic-value">{hilinkStatus.traffic?.current_upload || '0 B'}</span>
                    </div>
                  </div>

                  {/* Network Mode Selection */}
                  <div className="modem-mode-section">
                    <div className="modem-label">{t('network.networkMode', 'Network Mode')}</div>
                    <div className="network-mode-buttons">
                      {[
                        { mode: '00', label: 'Auto' },
                        { mode: '03', label: '4G' },
                        { mode: '02', label: '3G' },
                        { mode: '01', label: '2G' },
                      ].map((opt) => (
                        <button
                          key={opt.mode}
                          className={`mode-btn-small ${hilinkStatus.mode?.network_mode === opt.mode ? 'active' : ''}`}
                          onClick={() => handleSetNetworkMode(opt.mode)}
                          disabled={changingNetworkMode || hilinkStatus.mode?.network_mode === opt.mode}
                        >
                          {opt.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Connection Details */}
                  <div className="modem-details">
                    <div className="modem-detail">
                      <span className="modem-label">IP</span>
                      <span className="modem-value">{modem.ip_address || '-'}</span>
                    </div>
                    <div className="modem-detail">
                      <span className="modem-label">IMEI</span>
                      <span className="modem-value">{hilinkStatus.device?.imei?.slice(-8) || '-'}</span>
                    </div>
                    <div className="modem-detail">
                      <span className="modem-label">DNS</span>
                      <span className="modem-value">{hilinkStatus.network?.primary_dns || '-'}</span>
                    </div>
                    <div className="modem-detail">
                      <span className="modem-label">{t('network.connectTime', 'Uptime')}</span>
                      <span className="modem-value">
                        {hilinkStatus.traffic?.current_connect_time 
                          ? `${Math.floor(hilinkStatus.traffic.current_connect_time / 60)}m`
                          : '-'}
                      </span>
                    </div>
                  </div>

                  {/* Reboot Button */}
                  <button 
                    className="btn btn-modem-reboot"
                    onClick={handleRebootModem}
                  >
                    🔄 {t('network.rebootModem', 'Reboot Modem')}
                  </button>
                </>
              ) : modem.detected ? (
                <>
                  <div className={modem.connected ? 'modem-connected' : 'modem-disconnected'}>
                    <span>{modem.connected ? '✓' : '○'}</span>
                    <span>
                      {modem.connected 
                        ? t('network.modemConnected', 'Connected') 
                        : t('network.modemDisconnected', 'Disconnected')}
                    </span>
                  </div>
                  <div className="modem-details">
                    <div className="modem-detail">
                      <span className="modem-label">{t('network.interface', 'Interface')}</span>
                      <span className="modem-value">{modem.interface}</span>
                    </div>
                    <div className="modem-detail">
                      <span className="modem-label">{t('network.ipAddress', 'IP Address')}</span>
                      <span className="modem-value">{modem.ip_address}</span>
                    </div>
                  </div>
                  <div className="modem-api-hint">
                    {t('network.hilinkNotAvailable', 'HiLink API not available')}
                  </div>
                </>
              ) : (
                <div className="modem-not-detected">
                  <div className="icon">📵</div>
                  <div>{t('network.modemNotDetected', 'No 4G modem detected')}</div>
                  <div style={{ fontSize: '0.8rem', marginTop: '8px', opacity: 0.7 }}>
                    {t('network.modemHint', 'Connect a USB 4G modem (HiLink compatible)')}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* WiFi Connect Modal */}
      {connectModal.open && (
        <div className="wifi-modal-overlay" onClick={() => setConnectModal({ open: false, ssid: '', security: '' })}>
          <div className="wifi-modal" onClick={(e) => e.stopPropagation()}>
            <h3>
              {t('network.connectTo', 'Connect to')} <span className="wifi-modal-ssid">{connectModal.ssid}</span>
            </h3>
            
            {connectModal.security && connectModal.security !== '--' && (
              <div className="form-group">
                <label>{t('network.password', 'Password')}</label>
                <input
                  type="password"
                  value={wifiPassword}
                  onChange={(e) => setWifiPassword(e.target.value)}
                  placeholder={t('network.enterPassword', 'Enter WiFi password')}
                  autoFocus
                  onKeyDown={(e) => e.key === 'Enter' && handleWifiConnect()}
                />
              </div>
            )}
            
            <div className="wifi-modal-buttons">
              <button 
                className="btn-cancel" 
                onClick={() => setConnectModal({ open: false, ssid: '', security: '' })}
              >
                {t('common.cancel', 'Cancel')}
              </button>
              <button 
                className="btn-connect" 
                onClick={handleWifiConnect}
                disabled={connecting}
              >
                {connecting ? t('network.connecting', 'Connecting...') : t('network.connect', 'Connect')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default NetworkView
