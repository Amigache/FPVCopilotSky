import './NetworkView.css'
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../../../contexts/ToastContext'
import { useWebSocket } from '../../../contexts/WebSocketContext'
import api from '../../../services/api'
import { API_TIMEOUTS, UI_DELAYS, getSignalBars } from './networkConstants'

const NetworkView = () => {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { messages } = useWebSocket()

  // State
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState(null)
  const [hilinkStatus, setHilinkStatus] = useState(null)
  const [wifiNetworks, setWifiNetworks] = useState([])
  const [wifiScanning, setWifiScanning] = useState(false)
  const [changingMode, setChangingMode] = useState(false)

  // Flight Mode
  const [flightMode, setFlightMode] = useState(null)
  const [togglingFlightMode, setTogglingFlightMode] = useState(false)

  // WiFi Connect Modal
  const [connectModal, setConnectModal] = useState({ open: false, ssid: '', security: '' })
  const [wifiPassword, setWifiPassword] = useState('')
  const [connecting, setConnecting] = useState(false)

  // Mode Change Confirmation Modal
  const [modeChangeModal, setModeChangeModal] = useState({ open: false, targetMode: '' })

  // Load unified dashboard data (combines network, modem, wifi, flight mode)
  const loadDashboard = useCallback(async (forceRefresh = false) => {
    try {
      const url = forceRefresh
        ? '/api/network/dashboard?force_refresh=true'
        : '/api/network/dashboard'

      const response = await api.get(url, API_TIMEOUTS.DASHBOARD)
      if (response.ok) {
        const data = await response.json()

        // Update all states from unified response
        if (data.network) {
          setStatus(data.network)
        }
        if (data.modem) {
          setHilinkStatus(data.modem)
        }
        if (data.wifi_networks) {
          setWifiNetworks(data.wifi_networks)
        }
        if (data.flight_mode) {
          setFlightMode(data.flight_mode)
        }

        return data
      }
    } catch (error) {
      console.error('Error loading dashboard:', error)
      // Set fallback states
      setHilinkStatus({ available: false, connected: false })
    }
  }, [])

  // Load WiFi networks independently (for refresh button)
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

  // Initial load - use unified dashboard endpoint
  useEffect(() => {
    const loadAll = async () => {
      setLoading(true)
      setWifiScanning(true)
      await loadDashboard(true) // Force refresh on initial load
      setLoading(false)
      // Keep wifiScanning=true briefly to show spinner while networks load
      await new Promise((resolve) => setTimeout(resolve, UI_DELAYS.WIFI_SCAN_ANIMATION))
      setWifiScanning(false)
    }
    loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Toggle Flight Mode
  const handleToggleFlightMode = async () => {
    const isActive = flightMode?.flight_mode_active
    setTogglingFlightMode(true)

    try {
      const endpoint = isActive
        ? '/api/network/flight-mode/disable'
        : '/api/network/flight-mode/enable'

      const response = await api.post(endpoint)
      if (response.ok) {
        const data = await response.json()
        showToast(
          data.message || (isActive ? 'Flight Mode desactivado' : 'Flight Mode activado'),
          data.success ? 'success' : 'warning'
        )
        // Reload dashboard to get updated state
        await loadDashboard(true)
      } else {
        const data = await response.json()
        showToast(data.detail || 'Error al cambiar Flight Mode', 'error')
      }
    } catch (error) {
      showToast(error.message || 'Error al cambiar Flight Mode', 'error')
    }
    setTogglingFlightMode(false)
  }

  // Update from WebSocket - network status
  useEffect(() => {
    if (messages.network_status) {
      const prevModemDetected = status?.modem?.detected || false
      const newModemDetected = messages.network_status?.modem?.detected || false

      setStatus(messages.network_status)
      setLoading(false)

      // If modem was just detected, refresh dashboard to get HiLink status
      if (!prevModemDetected && newModemDetected) {
        loadDashboard(true)
      }
    }
  }, [messages.network_status, status?.modem?.detected, loadDashboard])

  // Update from WebSocket - modem HiLink status
  useEffect(() => {
    if (messages.modem_status) {
      setHilinkStatus(messages.modem_status)
    }
  }, [messages.modem_status])

  // Set priority mode
  const handleSetMode = async (mode) => {
    // Always show confirmation modal when changing mode
    if (mode !== status?.mode) {
      setModeChangeModal({ open: true, targetMode: mode })
      return
    }
  }

  // Perform the actual mode change
  const performModeChange = async (mode) => {
    setChangingMode(true)
    setModeChangeModal({ open: false, targetMode: '' })
    try {
      const response = await api.post('/api/network/priority', { mode })
      if (response.ok) {
        await loadDashboard(true) // Reload dashboard after mode change
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
        showToast(
          t('network.wifiConnected', 'Connected to {{ssid}}', { ssid: connectModal.ssid }),
          'success'
        )
        setConnectModal({ open: false, ssid: '', security: '' })
        await loadDashboard(true) // Reload dashboard after WiFi connect
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
        await loadDashboard(true) // Reload dashboard after WiFi disconnect
        await loadWifiNetworks()
      }
    } catch (error) {
      showToast(error.message, 'error')
    }
  }

  // Get signal bars count
  const getSignalBarsLocal = (signal) => getSignalBars(signal)

  if (loading) {
    return (
      <div className="card">
        <h2>🌐 {t('network.title', 'Network')}</h2>
        <div className="waiting-data">
          <div className="spinner-small"></div>
          {t('common.loadingContent', 'Cargando contenido')}
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
      <div
        className={`network-mode-banner ${
          currentMode === 'modem' ? 'modem-primary' : 'wifi-primary'
        }`}
      >
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
            disabled={changingMode || currentMode === 'wifi' || !status?.wifi_interface}
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
          <button
            className={`mode-btn flight-mode-btn ${flightMode?.flight_mode_active ? 'active' : ''}`}
            onClick={handleToggleFlightMode}
            disabled={togglingFlightMode || !modem.detected}
            title={
              flightMode?.flight_mode_active
                ? 'Flight Mode: Optimizaciones activas'
                : 'Activar Flight Mode (Optimización completa)'
            }
          >
            {togglingFlightMode ? '⏳' : flightMode?.flight_mode_active ? '🚀✓' : '🚀'} Flight
          </button>
        </div>
      </div>

      <div className="network-columns">
        {/* Left Column */}
        <div className="network-col">
          {/* Interfaces Card */}
          <div className="card">
            <h2>🔌 {t('network.interfaces', 'Interfaces')}</h2>
            <div className="interfaces-list">
              {interfaces.map((iface) => (
                <div
                  key={iface.name}
                  className={`interface-item ${
                    iface.state === 'UP' ? 'connected' : 'disconnected'
                  }`}
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
                      <td className={idx === 0 ? 'primary-route' : ''}>{route.interface}</td>
                      <td>{route.gateway}</td>
                      <td className={idx === 0 ? 'primary-route' : ''}>{route.metric || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="loading-indicator">{t('network.noRoutes', 'No default routes')}</div>
            )}
          </div>
        </div>

        {/* Right Column */}
        <div className="network-col">
          {/* WiFi Networks Card */}
          <div className="card">
            <div className="card-header">
              <h2>📡 {t('network.wifiNetworks', 'WiFi Networks')}</h2>
              <button className="btn-refresh" onClick={loadWifiNetworks} disabled={wifiScanning}>
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
                              className={`signal-bar ${
                                bar <= getSignalBarsLocal(network.signal) ? 'active' : ''
                              }`}
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
            <div className="card-header">
              <h2>📶 {t('network.modem4G', 'MÓDEM 4G')}</h2>
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
                          className={`signal-bar-large ${
                            bar <=
                            (hilinkStatus.signal?.signal_bars ||
                              Math.ceil((hilinkStatus.signal?.signal_percent || 0) / 20))
                              ? 'active'
                              : ''
                          }`}
                        />
                      ))}
                    </div>
                    <div className="signal-details">
                      <span className="signal-percent">
                        {hilinkStatus.signal?.signal_percent || 0}%
                      </span>
                      <span className="signal-rssi">{hilinkStatus.signal?.rssi || '-'}</span>
                    </div>
                  </div>

                  {/* Traffic Stats */}
                  <div className="modem-traffic">
                    <div className="traffic-stat">
                      <span className="traffic-icon">↓</span>
                      <span className="traffic-value">
                        {hilinkStatus.traffic?.current_download || '0 B'}
                      </span>
                    </div>
                    <div className="traffic-stat">
                      <span className="traffic-icon">↑</span>
                      <span className="traffic-value">
                        {hilinkStatus.traffic?.current_upload || '0 B'}
                      </span>
                    </div>
                  </div>

                  {/* Connection Details */}
                  <div className="modem-details">
                    <div className="modem-detail">
                      <span className="modem-label">IP</span>
                      <span className="modem-value">
                        {hilinkStatus.network?.ip_address || modem.ip_address || '-'}
                      </span>
                    </div>
                    <div className="modem-detail">
                      <span className="modem-label">IMEI</span>
                      <span className="modem-value">
                        {hilinkStatus.device?.imei?.slice(-8) || '-'}
                      </span>
                    </div>
                    <div className="modem-detail">
                      <span className="modem-label">DNS</span>
                      <span className="modem-value">
                        {hilinkStatus.network?.primary_dns || '-'}
                      </span>
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
        <div
          className="wifi-modal-overlay"
          onClick={() => setConnectModal({ open: false, ssid: '', security: '' })}
        >
          <div className="wifi-modal" onClick={(e) => e.stopPropagation()}>
            <h3>
              {t('network.connectTo', 'Connect to')}{' '}
              <span className="wifi-modal-ssid">{connectModal.ssid}</span>
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
              <button className="btn-connect" onClick={handleWifiConnect} disabled={connecting}>
                {connecting
                  ? t('network.connecting', 'Connecting...')
                  : t('network.connect', 'Connect')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Mode Change Confirmation Modal */}
      {modeChangeModal.open && (
        <div
          className="wifi-modal-overlay"
          onClick={() => setModeChangeModal({ open: false, targetMode: '' })}
        >
          <div className="wifi-modal" onClick={(e) => e.stopPropagation()}>
            <h3>⚠️ {t('network.confirmModeChange', 'Confirm Mode Change')}</h3>

            <div style={{ marginTop: '16px', marginBottom: '20px', lineHeight: '1.5' }}>
              <p>
                {modeChangeModal.targetMode === 'modem'
                  ? t(
                      'network.confirmModeChangeToModem',
                      '¿Are you sure you want to switch from WiFi to 4G as the primary connection?'
                    )
                  : t(
                      'network.confirmModeChangeToWifi',
                      '¿Are you sure you want to switch from 4G to WiFi as the primary connection?'
                    )}
              </p>
              <p style={{ marginTop: '8px', fontSize: '0.9rem', opacity: 0.8 }}>
                {t(
                  'network.confirmModeChangeWarning',
                  'This will change your default network route.'
                )}
              </p>
            </div>

            <div className="wifi-modal-buttons">
              <button
                className="btn-cancel"
                onClick={() => setModeChangeModal({ open: false, targetMode: '' })}
              >
                {t('common.cancel', 'Cancel')}
              </button>
              <button
                className="btn-connect"
                onClick={() => performModeChange(modeChangeModal.targetMode)}
                disabled={changingMode}
              >
                {changingMode
                  ? t('network.changing', 'Changing...')
                  : t('network.confirm', 'Confirm')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default NetworkView
