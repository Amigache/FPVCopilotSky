import './NetworkView.css'
import { useState, useEffect, useCallback, useRef } from 'react'

import { useTranslation } from 'react-i18next'
import { useToast } from '../../../contexts/ToastContext'
import { useWebSocket } from '../../../contexts/WebSocketContext'
import api from '../../../services/api'
import { API_TIMEOUTS, getSignalBars } from './networkConstants'

// Helper to format bitrate
function formatBitrate(val) {
  if (!val && val !== 0) return '—'
  if (val > 10000) return `${(val / 1000).toFixed(0)} Mbps`
  return `${val} kbps`
}

const NetworkView = () => {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { messages } = useWebSocket()

  // Video stats from WebSocket (as in VideoView)
  const videoStatus = messages.video_status || {}
  const videoStats = videoStatus.stats || {}
  const videoConfig = videoStatus.config || {}

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

  // Network Quality Bridge (Self-healing streaming)
  const [bridgeStatus, setBridgeStatus] = useState({
    active: false,
    check_interval: 2,
    signal_quality: 0,
    jitter_ms: 0,
    latency_ms: 0,
    recent_events: [],
  })
  const [bridgeInitialized, setBridgeInitialized] = useState(false)
  const [bridgeStarting, setBridgeStarting] = useState(false)
  const bridgePollRef = useRef(null)
  const bridgeStartAttemptRef = useRef(false)

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
      const response = await api.get('/api/network-interfaces/wifi/scan')
      if (response.ok) {
        const data = await response.json()
        setWifiNetworks(data.networks || [])
      }
    } catch (error) {
      console.error('Error loading WiFi networks:', error)
    }
    setWifiScanning(false)
  }, [])

  // Initial load - dashboard for status, separate WiFi scan
  useEffect(() => {
    const loadAll = async () => {
      setLoading(true)
      setWifiScanning(true)
      // Load dashboard (network status, modem, flight mode - NO WiFi scan)
      await loadDashboard(true)
      setLoading(false)
      // Scan WiFi networks separately (only real scan trigger)
      await loadWifiNetworks()
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

  // Update from WebSocket - network quality bridge
  useEffect(() => {
    if (messages.network_quality) {
      setBridgeStatus(messages.network_quality)
      if (!bridgeInitialized) {
        setBridgeInitialized(true)
      }
    }
  }, [messages.network_quality, bridgeInitialized])

  // Auto-start bridge if inactive
  const startBridge = useCallback(async () => {
    if (bridgeStarting || bridgeStartAttemptRef.current) return

    setBridgeStarting(true)
    bridgeStartAttemptRef.current = true

    try {
      const response = await api.post('/api/network/bridge/start')
      if (response.ok) {
        console.log('Bridge started successfully')
        // Wait a bit and refresh status
        await new Promise((resolve) => setTimeout(resolve, 1000))
        const statusResponse = await api.get('/api/network/bridge/status', 5000)
        if (statusResponse.ok) {
          const data = await statusResponse.json()
          if (data.success) {
            setBridgeStatus(data)
          }
        }
      }
    } catch (error) {
      console.error('Error starting bridge:', error)
    } finally {
      setBridgeStarting(false)
    }
  }, [bridgeStarting])

  // Poll bridge status - initial load and periodic refresh
  useEffect(() => {
    const pollBridge = async () => {
      try {
        const response = await api.get('/api/network/bridge/status', 5000)
        if (response.ok) {
          const data = await response.json()
          if (data.success) {
            setBridgeStatus(data)
            if (!bridgeInitialized) {
              setBridgeInitialized(true)
            }
            // Auto-start if inactive (only once)
            if (data.active === false && !bridgeStartAttemptRef.current) {
              console.log('Bridge inactive, auto-starting...')
              startBridge()
            }
          }
        }
      } catch {
        /* ignore */
      }
    }
    // Initial load
    pollBridge()
    // Poll every 10s as fallback (WebSocket is primary source)
    bridgePollRef.current = setInterval(pollBridge, 10000)
    return () => clearInterval(bridgePollRef.current)
  }, [bridgeInitialized, startBridge])

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

      const response = await api.post('/api/network-interfaces/wifi/connect', payload)
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
      const response = await api.post('/api/network-interfaces/wifi/disconnect')
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
          {/* Network Quality Bridge Card - Always Active - Moved to top */}
          <div className="card network-bridge-card">
            <h2>📊 {t('network.qualityBridge', 'Calidad de Red')}</h2>

            {bridgeStatus?.quality_score ? (
              (() => {
                const qs = bridgeStatus.quality_score
                const score = qs.score || 0

                // Si el servicio no está activo, mostrar mensaje con botón de reinicio
                if (bridgeStatus.active === false && bridgeInitialized) {
                  return (
                    <div className="bridge-inactive">
                      <div className="bridge-inactive-icon">{bridgeStarting ? '⏳' : '⚠️'}</div>
                      <div>
                        {bridgeStarting
                          ? 'Iniciando monitoreo...'
                          : 'Servicio de monitoreo inactivo'}
                      </div>
                      <div className="bridge-inactive-hint">
                        {bridgeStarting
                          ? 'Espera unos segundos...'
                          : 'Intentando iniciar automáticamente...'}
                      </div>
                      {!bridgeStarting && (
                        <button
                          className="btn-primary"
                          onClick={startBridge}
                          style={{ marginTop: '12px' }}
                        >
                          🔄 Reintentar manualmente
                        </button>
                      )}
                    </div>
                  )
                }

                const scoreColor =
                  score >= 80
                    ? '#4caf50'
                    : score >= 60
                      ? '#8bc34a'
                      : score >= 40
                        ? '#ff9800'
                        : score >= 20
                          ? '#f44336'
                          : '#b71c1c'
                const trendIcon =
                  qs.trend === 'improving' ? '📈' : qs.trend === 'degrading' ? '📉' : '➡️'
                const cell = bridgeStatus.cell_state || {}
                const lat = bridgeStatus.latency || {}
                const events = bridgeStatus.recent_events || []
                const lastEvents = events.slice(-5).reverse()

                // Use primary_type from bridge to determine connection mode
                const primaryType = bridgeStatus.primary_type || 'unknown'
                const hasModem = primaryType === 'modem'

                return (
                  <div className="bridge-content">
                    {/* Two-column layout: Score on left, Metrics on right */}
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: '1fr 1fr',
                        gap: '20px',
                        marginBottom: '16px',
                      }}
                    >
                      {/* Left Column: Score Ring & Trend */}
                      <div
                        className="bridge-score-section"
                        style={{
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        <div
                          className="score-ring"
                          style={{
                            '--score-color': scoreColor,
                            '--score-pct': `${score}%`,
                            width: '140px',
                            height: '140px',
                          }}
                        >
                          <div
                            className="score-value"
                            style={{ color: scoreColor, fontSize: '2.5rem' }}
                          >
                            {Math.round(score)}
                          </div>
                          <div className="score-label" style={{ fontSize: '0.95rem' }}>
                            {qs.label}
                          </div>
                        </div>
                        <div
                          className="score-trend"
                          style={{ marginTop: '12px', fontSize: '1rem' }}
                        >
                          {trendIcon}{' '}
                          {qs.trend === 'improving'
                            ? 'Mejorando'
                            : qs.trend === 'degrading'
                              ? 'Degradando'
                              : 'Estable'}
                        </div>
                      </div>

                      {/* Right Column: Metrics in vertical layout */}
                      <div
                        className="bridge-metrics"
                        style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}
                      >
                        {/* SINR - Only relevant for modem connections */}
                        {hasModem ? (
                          <div className="bridge-metric">
                            <span className="metric-label">SINR</span>
                            <span
                              className="metric-value"
                              style={{
                                color:
                                  (cell.sinr || 0) > 10
                                    ? '#4caf50'
                                    : (cell.sinr || 0) > 5
                                      ? '#ff9800'
                                      : '#f44336',
                              }}
                            >
                              {cell.sinr != null ? `${cell.sinr.toFixed(1)} dB` : '\u2014'}
                            </span>
                            <div className="metric-bar">
                              <div
                                className="metric-bar-fill"
                                style={{
                                  width: `${
                                    cell.sinr != null
                                      ? Math.min(100, Math.max(0, ((cell.sinr + 5) * 100) / 30))
                                      : 0
                                  }%`,
                                  background: scoreColor,
                                }}
                              />
                            </div>
                          </div>
                        ) : (
                          /* WiFi/Ethernet: Show connection type instead of SINR */
                          <div className="bridge-metric">
                            <span className="metric-label">Conexión</span>
                            <span className="metric-value" style={{ color: '#2196f3' }}>
                              {primaryType === 'wifi'
                                ? '📶 WiFi'
                                : primaryType === 'ethernet'
                                  ? '🔌 Ethernet'
                                  : '🌐 Red'}
                            </span>
                            <div className="metric-bar">
                              <div
                                className="metric-bar-fill"
                                style={{
                                  width: `${Math.max(0, 100 - (lat.rtt_ms || 0) / 4)}%`,
                                  background:
                                    (lat.rtt_ms || 0) < 50
                                      ? '#4caf50'
                                      : (lat.rtt_ms || 0) < 150
                                        ? '#ff9800'
                                        : '#f44336',
                                }}
                              />
                            </div>
                          </div>
                        )}
                        <div className="bridge-metric">
                          <span className="metric-label">RTT</span>
                          <span
                            className="metric-value"
                            style={{
                              color:
                                lat.rtt_ms < 100
                                  ? '#4caf50'
                                  : lat.rtt_ms < 200
                                    ? '#ff9800'
                                    : '#f44336',
                            }}
                          >
                            {lat.rtt_ms != null && lat.rtt_ms !== undefined
                              ? `${lat.rtt_ms} ms`
                              : '\u2014'}
                          </span>
                          <div className="metric-bar">
                            <div
                              className="metric-bar-fill"
                              style={{
                                width: `${
                                  lat.rtt_ms != null ? Math.max(0, 100 - lat.rtt_ms / 4) : 0
                                }%`,
                                background: lat.rtt_ms < 100 ? '#4caf50' : '#ff9800',
                              }}
                            />
                          </div>
                        </div>
                        <div className="bridge-metric">
                          <span className="metric-label">Jitter</span>
                          <span
                            className="metric-value"
                            style={{
                              color:
                                lat.jitter_ms < 20
                                  ? '#4caf50'
                                  : lat.jitter_ms < 50
                                    ? '#ff9800'
                                    : '#f44336',
                            }}
                          >
                            {lat.jitter_ms != null && lat.jitter_ms !== undefined
                              ? `${lat.jitter_ms} ms`
                              : '\u2014'}
                          </span>
                          <div className="metric-bar">
                            <div
                              className="metric-bar-fill"
                              style={{
                                width: `${
                                  lat.jitter_ms != null ? Math.max(0, 100 - lat.jitter_ms) : 0
                                }%`,
                                background: lat.jitter_ms < 20 ? '#4caf50' : '#ff9800',
                              }}
                            />
                          </div>
                        </div>
                        <div className="bridge-metric">
                          <span className="metric-label">Pérdida</span>
                          <span
                            className="metric-value"
                            style={{
                              color:
                                lat.packet_loss < 2
                                  ? '#4caf50'
                                  : lat.packet_loss < 5
                                    ? '#ff9800'
                                    : '#f44336',
                            }}
                          >
                            {lat.packet_loss != null && lat.packet_loss !== undefined
                              ? `${lat.packet_loss}%`
                              : '\u2014'}
                          </span>
                          <div className="metric-bar">
                            <div
                              className="metric-bar-fill"
                              style={{
                                width: `${
                                  lat.packet_loss != null
                                    ? Math.max(0, 100 - lat.packet_loss * 5)
                                    : 0
                                }%`,
                                background: lat.packet_loss < 2 ? '#4caf50' : '#f44336',
                              }}
                            />
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Info note about connection mode */}
                    {!hasModem && (
                      <div
                        style={{
                          padding: '8px 12px',
                          background: 'rgba(33, 150, 243, 0.1)',
                          border: '1px solid rgba(33, 150, 243, 0.3)',
                          borderRadius: '6px',
                          marginBottom: '12px',
                          fontSize: '0.85rem',
                          color: '#2196f3',
                        }}
                      >
                        ℹ️ Conectado vía {primaryType === 'wifi' ? 'WiFi' : 'Ethernet'} — Calidad
                        basada en latencia
                      </div>
                    )}
                    {hasModem && (
                      <div
                        style={{
                          padding: '8px 12px',
                          background: 'rgba(76, 175, 80, 0.1)',
                          border: '1px solid rgba(76, 175, 80, 0.3)',
                          borderRadius: '6px',
                          marginBottom: '12px',
                          fontSize: '0.85rem',
                          color: '#4caf50',
                        }}
                      >
                        📡 Modo 4G — {cell.operator || 'Operador'}{' '}
                        {cell.network_type ? `(${cell.network_type})` : ''}{' '}
                        {cell.band ? `B${cell.band}` : ''}
                      </div>
                    )}

                    {/* Actual vs Recommended Video Stats */}
                    <div className="bridge-recommended">
                      <span className="rec-item" title="Actual bitrate">
                        🎥 <b>{formatBitrate(videoStats.current_bitrate)}</b>
                        <span style={{ opacity: 0.6, marginLeft: 4, marginRight: 4 }}>/</span>
                        <span title="Recomendado">
                          {qs.recommended?.bitrate_kbps
                            ? `${qs.recommended.bitrate_kbps} kbps`
                            : '—'}
                        </span>
                      </span>
                      <span className="rec-item" title="Actual resolución">
                        📐{' '}
                        <b>
                          {videoConfig.width && videoConfig.height
                            ? `${videoConfig.width}x${videoConfig.height}`
                            : '—'}
                        </b>
                        <span style={{ opacity: 0.6, marginLeft: 4, marginRight: 4 }}>/</span>
                        <span title="Recomendado">{qs.recommended?.resolution || '—'}</span>
                      </span>
                      <span className="rec-item" title="Actual FPS">
                        🎞️ <b>{videoConfig.framerate || videoStats.current_fps || '—'} fps</b>
                        <span style={{ opacity: 0.6, marginLeft: 4, marginRight: 4 }}>/</span>
                        <span title="Recomendado">{qs.recommended?.framerate || '—'} fps</span>
                      </span>
                    </div>

                    {/* Cell Info */}
                    {cell.cell_id && (
                      <div className="bridge-cell-info">
                        <span>📡 Cell: {cell.cell_id}</span>
                        <span>PCI: {cell.pci}</span>
                        <span>Band: {cell.band}</span>
                        <span>{cell.network_type}</span>
                      </div>
                    )}

                    {/* Recent Events */}
                    <div className="bridge-events">
                      <div className="events-title">Eventos recientes</div>
                      {lastEvents.length > 0 ? (
                        lastEvents.map((ev, idx) => {
                          const eventIcons = {
                            cell_change: '🔄',
                            band_change: '📶',
                            sinr_drop: '📉',
                            sinr_recovery: '📈',
                            high_jitter: '⚡',
                            jitter_recovery: '✅',
                            high_rtt: '🐢',
                            rtt_recovery: '✅',
                            packet_loss: '📦',
                            packet_loss_recovery: '✅',
                            disconnection: '❌',
                            reconnection: '🔁',
                          }
                          const icon = eventIcons[ev.event] || '📋'
                          const time = new Date(ev.timestamp * 1000).toLocaleTimeString('es-ES', {
                            hour: '2-digit',
                            minute: '2-digit',
                            second: '2-digit',
                          })
                          return (
                            <div key={idx} className="bridge-event-item">
                              <span className="event-icon">{icon}</span>
                              <span className="event-name">{ev.event.replace(/_/g, ' ')}</span>
                              {ev.actions?.length > 0 && (
                                <span className="event-actions">→ {ev.actions.join(', ')}</span>
                              )}
                              <span className="event-time">{time}</span>
                            </div>
                          )
                        })
                      ) : (
                        <div
                          className="bridge-event-item"
                          style={{ opacity: 0.6, fontStyle: 'italic' }}
                        >
                          <span>Sin eventos recientes</span>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })()
            ) : (
              <div className="bridge-inactive">
                <div className="bridge-inactive-icon">📊</div>
                <div>Recopilando datos...</div>
                <div className="bridge-inactive-hint">Las métricas aparecerán en unos segundos</div>
              </div>
            )}
          </div>

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
            <h2>📶 {t('network.modem4G', 'MÓDEM 4G')}</h2>
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
                  <div>{t('network.modemNotDetected', 'Modem not detected')}</div>
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
