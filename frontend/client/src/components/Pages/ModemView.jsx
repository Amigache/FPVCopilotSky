import './ModemView.css'
import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../../contexts/ToastContext'
import { useModal } from '../../contexts/ModalContext'
import api from '../../services/api'

const ModemView = () => {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { showModal } = useModal()
  
  // State
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState(null)
  const [bandPresets, setBandPresets] = useState(null)
  const [videoQuality, setVideoQuality] = useState(null)
  const [latency, setLatency] = useState(null)
  const [flightSession, setFlightSession] = useState(null)
  
  // Loading states
  const [changingBand, setChangingBand] = useState(false)
  const [changingMode, setChangingMode] = useState(false)
  const [togglingVideoMode, setTogglingVideoMode] = useState(false)
  const [testingLatency, setTestingLatency] = useState(false)
  const [reconnecting, setReconnecting] = useState(false)
  const [modemRebooting, setModemRebooting] = useState(false)
  
  // Flight session sampling
  const sampleIntervalRef = useRef(null)

  // Load modem status
  const loadStatus = useCallback(async () => {
    try {
      const response = await api.get('/api/network/hilink/status/enhanced', 15000)
      if (response.ok) {
        const data = await response.json()
        setStatus(data)
        if (data.video_quality) setVideoQuality(data.video_quality)
        if (data.latency) setLatency(data.latency)
      } else {
        setStatus({ available: false })
      }
    } catch (error) {
      setStatus({ available: false, error: error.message })
    }
  }, [])

  // Load band presets
  const loadBandPresets = useCallback(async () => {
    try {
      const response = await api.get('/api/network/hilink/band/presets')
      if (response.ok) {
        const data = await response.json()
        setBandPresets(data)
      }
    } catch (error) {
      console.error('Error loading band presets:', error)
    }
  }, [])

  // Load flight session status
  const loadFlightSession = useCallback(async () => {
    try {
      const response = await api.get('/api/network/hilink/flight-session')
      if (response.ok) {
        const data = await response.json()
        setFlightSession(data)
      }
    } catch (error) {
      // Ignore
    }
  }, [])

  // Initial load
  useEffect(() => {
    const loadAll = async () => {
      setLoading(true)
      await Promise.all([
        loadStatus(),
        loadBandPresets(),
        loadFlightSession()
      ])
      setLoading(false)
    }
    loadAll()
  }, [loadStatus, loadBandPresets, loadFlightSession])

  // Auto-refresh every 10 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      loadStatus()
    }, 10000)
    return () => clearInterval(interval)
  }, [loadStatus])

  // Set LTE band
  const handleSetBand = async (preset) => {
    setChangingBand(true)
    showToast('⏳ Cambiando banda LTE...', 'info')
    try {
      const response = await api.post('/api/network/hilink/band', { preset }, 20000)
      if (response.ok) {
        const data = await response.json()
        showToast(`✅ Banda cambiada: ${data.preset_name}`, 'success')
        await loadStatus()
      } else {
        const data = await response.json()
        showToast(data.detail || 'Error al cambiar banda', 'error')
      }
    } catch (error) {
      showToast(error.message, 'error')
    }
    setChangingBand(false)
  }

  // Set network mode
  const handleSetNetworkMode = async (mode) => {
    setChangingMode(true)
    showToast('⏳ Cambiando modo de red...', 'info')
    try {
      const response = await api.post('/api/network/hilink/mode', { mode }, 20000)
      if (response.ok) {
        showToast('✅ Modo de red cambiado', 'success')
        await loadStatus()
      } else {
        const data = await response.json()
        showToast(data.detail || 'Error', 'error')
      }
    } catch (error) {
      showToast(error.message, 'error')
    }
    setChangingMode(false)
  }

  // Toggle video mode
  const handleToggleVideoMode = async () => {
    setTogglingVideoMode(true)
    const actionMsg = status?.video_mode_active ? 'Desactivando' : 'Activando'
    showToast(`⏳ ${actionMsg} modo video...`, 'info')
    try {
      const endpoint = status?.video_mode_active 
        ? '/api/network/hilink/video-mode/disable'
        : '/api/network/hilink/video-mode/enable'
      
      const response = await api.post(endpoint, {}, 20000)
      if (response.ok) {
        const data = await response.json()
        showToast(`✅ ${data.message}`, 'success')
        await loadStatus()
      } else {
        const data = await response.json()
        showToast(data.detail || 'Error', 'error')
      }
    } catch (error) {
      showToast(error.message, 'error')
    }
    setTogglingVideoMode(false)
  }

  // Test latency
  const handleTestLatency = async () => {
    setTestingLatency(true)
    try {
      const response = await api.get('/api/network/hilink/latency')
      if (response.ok) {
        const data = await response.json()
        setLatency(data)
      } else {
        const data = await response.json()
        showToast(data.detail || 'Error en test de latencia', 'error')
      }
    } catch (error) {
      showToast(error.message, 'error')
    }
    setTestingLatency(false)
  }

  // Reconnect network
  const handleReconnect = async () => {
    setReconnecting(true)
    showToast('⏳ Reconectando a la red...', 'info')
    try {
      const response = await api.post('/api/network/hilink/reconnect', {}, 20000)
      if (response.ok) {
        showToast('✅ Reconexión iniciada', 'success')
        // Wait and refresh
        setTimeout(async () => {
          await loadStatus()
          setReconnecting(false)
        }, 5000)
        return
      } else {
        const data = await response.json()
        showToast(data.detail || 'Error', 'error')
      }
    } catch (error) {
      showToast(error.message, 'error')
    }
    setReconnecting(false)
  }

  // Start flight session
  const handleStartFlightSession = async () => {
    try {
      const response = await api.post('/api/network/hilink/flight-session/start')
      if (response.ok) {
        showToast('Sesión de vuelo iniciada', 'success')
        await loadFlightSession()
        
        // Start periodic sampling
        sampleIntervalRef.current = setInterval(async () => {
          await api.post('/api/network/hilink/flight-session/sample')
        }, 5000) // Sample every 5 seconds
      }
    } catch (error) {
      showToast(error.message, 'error')
    }
  }

  // Stop flight session
  const handleStopFlightSession = async () => {
    // Clear sampling interval
    if (sampleIntervalRef.current) {
      clearInterval(sampleIntervalRef.current)
      sampleIntervalRef.current = null
    }
    
    try {
      const response = await api.post('/api/network/hilink/flight-session/stop')
      if (response.ok) {
        const data = await response.json()
        showToast('Sesión de vuelo finalizada', 'success')
        
        // Show session summary modal
        showModal({
          title: 'Resumen de Sesión',
          message: formatSessionSummary(data.session_stats),
          type: 'info',
          confirmText: 'Cerrar'
        })
        
        setFlightSession({ active: false })
      }
    } catch (error) {
      showToast(error.message, 'error')
    }
  }

  // Format session summary
  const formatSessionSummary = (stats) => {
    if (!stats) return 'Sin datos'
    
    const duration = Math.floor(stats.duration_seconds / 60)
    return `
Duración: ${duration} minutos
Muestras: ${stats.sample_count}
SINR: ${stats.min_sinr?.toFixed(1) || 'N/A'} - ${stats.max_sinr?.toFixed(1) || 'N/A'} dB
RSRP: ${stats.min_rsrp?.toFixed(0) || 'N/A'} - ${stats.max_rsrp?.toFixed(0) || 'N/A'} dBm
Latencia promedio: ${stats.avg_latency_ms?.toFixed(0) || 'N/A'} ms
Cambios de banda: ${stats.band_changes}
    `.trim()
  }

  // Reboot modem
  const handleRebootModem = () => {
    showModal({
      title: 'Reiniciar Módem',
      message: '¿Estás seguro de que quieres reiniciar el módem 4G? Se perderá la conexión temporalmente.',
      type: 'confirm',
      confirmText: 'Reiniciar',
      cancelText: 'Cancelar',
      onConfirm: async () => {
        try {
          setModemRebooting(true)
          const response = await api.post('/api/network/hilink/reboot')
          if (response.ok) {
            showToast('⏳ Módem reiniciándose...', 'info')
            
            // Poll for modem to come back online (check every 5s for up to 60s)
            let attempts = 0
            const maxAttempts = 12
            const checkModem = async () => {
              attempts++
              try {
                const checkResponse = await api.get('/api/network/hilink/status', 5000)
                if (checkResponse.ok) {
                  const data = await checkResponse.json()
                  if (data.available) {
                    setModemRebooting(false)
                    showToast('✅ Módem en línea', 'success')
                    await loadStatus()
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
                showToast('⚠️ El módem no respondió. Verifica la conexión.', 'warning')
              }
            }
            
            // Start checking after initial delay
            setTimeout(checkModem, 10000)
          } else {
            setModemRebooting(false)
            const data = await response.json()
            showToast(data.detail || 'Error', 'error')
          }
        } catch (error) {
          setModemRebooting(false)
          showToast(error.message, 'error')
        }
      }
    })
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (sampleIntervalRef.current) {
        clearInterval(sampleIntervalRef.current)
      }
    }
  }, [])

  // Get quality color class
  const getQualityColorClass = (level) => {
    switch (level) {
      case 'excellent': return 'quality-excellent'
      case 'good': return 'quality-good'
      case 'moderate': return 'quality-moderate'
      case 'poor': return 'quality-poor'
      case 'critical': return 'quality-critical'
      default: return 'quality-unknown'
    }
  }

  if (loading) {
    return (
      <div className="card">
        <h2>📶 Módem</h2>
        <div className="waiting-data">
          <div className="spinner-small"></div>
          {t('common.loadingContent', 'Cargando contenido')}
        </div>
      </div>
    )
  }

  if (!status?.available) {
    return (
      <div className="modem-view">
        <div className="card modem-offline">
          <h2>📶 Módem</h2>
          <div className="offline-message">
            <span className="offline-icon">❌</span>
            <p>Módem no detectado o no disponible</p>
            <p className="offline-hint">Verifica que el módem USB esté conectado</p>
            <button className="btn-primary" onClick={loadStatus}>
              🔄 Reintentar
            </button>
          </div>
        </div>
      </div>
    )
  }

  const device = status.device || {}
  const signal = status.signal || {}
  const network = status.network || {}
  const currentBand = status.current_band || {}
  const traffic = status.traffic || {}

  return (
    <div className="modem-view">
      {/* Video Mode Banner */}
      <div className={`video-mode-banner ${status.video_mode_active ? 'active' : 'inactive'}`}>
        <div className="banner-info">
          <span className="banner-icon">{status.video_mode_active ? '🎬' : '📶'}</span>
          <div className="banner-text">
            <span className="banner-title">
              {status.video_mode_active ? 'Modo Video Activo' : 'Modo Normal'}
            </span>
            <span className="banner-description">
              {status.video_mode_active 
                ? '4G Only + Optimización para streaming' 
                : 'Configuración estándar del módem'}
            </span>
          </div>
        </div>
        <button 
          className={`btn-video-mode ${status.video_mode_active ? 'active' : ''}`}
          onClick={handleToggleVideoMode}
          disabled={togglingVideoMode}
        >
          {togglingVideoMode ? '⏳' : status.video_mode_active ? '⏹️ Desactivar' : '🎬 Activar Modo Video'}
        </button>
      </div>

      <div className="modem-sections">
        {/* === CARD 1: INFO - Operador & Dispositivo === */}
        <div className="card info-card">
          <h2>📡 Información</h2>
          <div className="info-sections">
            {/* Operador Section */}
            <div className="info-section operator-section">
              <div className="section-header">
                <span className="section-title">Operador</span>
                <span className={`connection-badge ${network.connection_status === 'Connected' ? 'connected' : 'disconnected'}`}>
                  {network.connection_status === 'Connected' ? '● Conectado' : '○ Desconectado'}
                </span>
              </div>
              <div className="operator-main-info">
                <span className="operator-name">{network.operator || 'Desconocido'}</span>
                <span className="tech-badge">{network.network_type_ex || network.network_type || '-'}</span>
              </div>
              <div className="info-grid">
                <div className="info-item">
                  <span className="info-label">MCC-MNC</span>
                  <span className="info-value mono">{network.operator_code || '-'}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">DNS</span>
                  <span className="info-value mono small">{network.primary_dns || '-'}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Roaming</span>
                  <span className={`info-value ${network.roaming ? 'warning' : ''}`}>
                    {network.roaming ? '⚠️ Activo' : 'No'}
                  </span>
                </div>
                <div className="info-item">
                  <span className="info-label">Señal</span>
                  <span className="info-value">{'📶'.repeat(network.signal_icon || 0)}</span>
                </div>
              </div>
            </div>

            <div className="section-divider"></div>

            {/* Dispositivo Section */}
            <div className="info-section device-section">
              <div className="section-header">
                <span className="section-title">Dispositivo</span>
              </div>
              <div className="info-grid">
                <div className="info-item">
                  <span className="info-label">Modelo</span>
                  <span className="info-value">{device.device_name || '-'}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">IMEI</span>
                  <span className="info-value mono small">{device.imei || '-'}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Hardware</span>
                  <span className="info-value">{device.hardware_version || '-'}</span>
                </div>
                <div className="info-item">
                  <span className="info-label">Firmware</span>
                  <span className="info-value">{device.software_version || '-'}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* === CARD 2: KPIs - Calidad, Latencia, Señal, Tráfico === */}
        <div className="card kpi-card">
          <h2>📊 Métricas de Rendimiento</h2>
          
          <div className="kpi-sections">
            {/* Video Quality Section */}
            <div className="kpi-section">
              <div className="kpi-header">
                <span className="kpi-title">🎬 Calidad Video</span>
              </div>
              {videoQuality?.available ? (
                <div className="kpi-content">
                  <div className={`quality-badge ${getQualityColorClass(videoQuality.quality)}`}>
                    <span className="quality-text">{videoQuality.label}</span>
                    <span className="quality-bitrate">{videoQuality.max_bitrate_kbps} kbps</span>
                  </div>
                  <div className="quality-rec">
                    Resolución: <strong>{videoQuality.recommended_resolution}</strong>
                  </div>
                  {videoQuality.warnings?.length > 0 && (
                    <div className="quality-warnings">
                      {videoQuality.warnings.map((w, i) => (
                        <span key={i} className="warning-tag">⚠️ {w}</span>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div className="kpi-no-data">Sin datos</div>
              )}
            </div>

            {/* Latency Section */}
            <div className="kpi-section">
              <div className="kpi-header">
                <span className="kpi-title">⏱️ Latencia</span>
                <button 
                  className="btn-mini" 
                  onClick={handleTestLatency}
                  disabled={testingLatency}
                >
                  {testingLatency ? '...' : '🔄'}
                </button>
              </div>
              {latency?.success ? (
                <div className="kpi-content">
                  <div className={`latency-badge ${getQualityColorClass(latency.quality?.level)}`}>
                    <span className="latency-main">{latency.avg_ms} ms</span>
                    <span className="latency-label">{latency.quality?.label}</span>
                  </div>
                  <div className="latency-details">
                    <span>Min: {latency.min_ms}ms</span>
                    <span>Max: {latency.max_ms}ms</span>
                    <span>Jitter: {latency.jitter_ms}ms</span>
                  </div>
                </div>
              ) : (
                <div className="kpi-no-data">
                  <button className="btn-small" onClick={handleTestLatency} disabled={testingLatency}>
                    {testingLatency ? 'Probando...' : 'Probar'}
                  </button>
                </div>
              )}
            </div>

            {/* Signal Section */}
            <div className="kpi-section signal-section">
              <div className="kpi-header">
                <span className="kpi-title">📶 Señal LTE</span>
              </div>
              <div className="signal-grid-compact">
                <div className="signal-metric">
                  <span className="metric-name">RSSI</span>
                  <span className="metric-val">{signal.rssi || '-'}</span>
                </div>
                <div className="signal-metric">
                  <span className="metric-name">RSRP</span>
                  <span className="metric-val">{signal.rsrp || '-'}</span>
                </div>
                <div className="signal-metric">
                  <span className="metric-name">RSRQ</span>
                  <span className="metric-val">{signal.rsrq || '-'}</span>
                </div>
                <div className="signal-metric">
                  <span className="metric-name">SINR</span>
                  <span className="metric-val">{signal.sinr || '-'}</span>
                </div>
                <div className="signal-metric">
                  <span className="metric-name">Cell</span>
                  <span className="metric-val small">{signal.cell_id || '-'}</span>
                </div>
                <div className="signal-metric">
                  <span className="metric-name">PCI</span>
                  <span className="metric-val">{signal.pci || '-'}</span>
                </div>
              </div>
            </div>

            {/* Traffic Section */}
            <div className="kpi-section">
              <div className="kpi-header">
                <span className="kpi-title">📈 Tráfico</span>
              </div>
              <div className="traffic-grid-compact">
                <div className="traffic-metric">
                  <span className="traffic-icon">⬇️</span>
                  <span className="traffic-val">{traffic.current_download || '-'}</span>
                </div>
                <div className="traffic-metric">
                  <span className="traffic-icon">⬆️</span>
                  <span className="traffic-val">{traffic.current_upload || '-'}</span>
                </div>
                <div className="traffic-total">
                  Total: ⬇️ {traffic.total_download || '-'} / ⬆️ {traffic.total_upload || '-'}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* === CARD 3: CONFIGURACIÓN - Banda, Modo, Sesión === */}
        <div className="card config-card">
          <h2>⚙️ Configuración</h2>
          
          <div className="config-sections">
            {/* Band Config */}
            <div className="config-section">
              <div className="config-header">
                <span className="config-title">📡 Banda LTE</span>
                <button 
                  className="btn-mini" 
                  onClick={handleReconnect}
                  disabled={reconnecting}
                  title="Reconectar"
                >
                  {reconnecting ? '...' : '🔁'}
                </button>
              </div>
              
              {changingBand && (
                <div className="config-loading">⏳ Aplicando...</div>
              )}
              
              <div className="band-info">
                <span className="band-enabled">
                  Habilitadas: <strong>{currentBand.enabled_bands?.length > 0 
                    ? currentBand.enabled_bands.join(', ') 
                    : 'Todas'}</strong>
                </span>
              </div>
              
              <div className="preset-grid">
                {bandPresets?.presets && Object.entries(bandPresets.presets).map(([key, preset]) => (
                  <button
                    key={key}
                    className="btn-preset-compact"
                    onClick={() => handleSetBand(key)}
                    disabled={changingBand}
                    title={preset.description}
                  >
                    {preset.name}
                  </button>
                ))}
              </div>
            </div>

            <div className="config-divider"></div>

            {/* Network Mode */}
            <div className="config-section">
              <div className="config-header">
                <span className="config-title">📶 Modo de Red</span>
              </div>
              
              {changingMode && (
                <div className="config-loading">⏳ Cambiando...</div>
              )}
              
              <div className="current-mode-info">
                Actual: <strong>{status.mode?.network_mode_name || network.network_type || '-'}</strong>
              </div>
              
              <div className="mode-grid">
                <button 
                  className={`btn-mode-compact ${status.mode?.network_mode === '00' ? 'active' : ''}`}
                  onClick={() => handleSetNetworkMode('00')}
                  disabled={changingMode}
                >
                  Auto
                </button>
                <button 
                  className={`btn-mode-compact ${status.mode?.network_mode === '03' ? 'active' : ''}`}
                  onClick={() => handleSetNetworkMode('03')}
                  disabled={changingMode}
                >
                  4G Only
                </button>
                <button 
                  className={`btn-mode-compact ${status.mode?.network_mode === '02' ? 'active' : ''}`}
                  onClick={() => handleSetNetworkMode('02')}
                  disabled={changingMode}
                >
                  3G Only
                </button>
              </div>
            </div>

            <div className="config-divider"></div>

            {/* Flight Session */}
            <div className="config-section">
              <div className="config-header">
                <span className="config-title">✈️ Sesión de Vuelo</span>
              </div>
              
              {flightSession?.active ? (
                <div className="session-active-compact">
                  <div className="session-status">
                    <span className="recording-dot">🔴</span>
                    <span>Grabando - {flightSession.stats?.sample_count || 0} muestras</span>
                  </div>
                  <button className="btn-stop" onClick={handleStopFlightSession}>
                    ⏹️ Detener
                  </button>
                </div>
              ) : (
                <div className="session-inactive">
                  <span className="session-hint">Graba estadísticas durante el vuelo</span>
                  <button className="btn-start" onClick={handleStartFlightSession}>
                    ▶️ Iniciar
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Reboot Section */}
          <div className="config-group reboot-section">
            <h3>🔄 Reinicio</h3>
            <div className="reboot-container">
              <span className="reboot-hint">Reinicia el módem si hay problemas de conexión</span>
              <button 
                className="btn-reboot" 
                onClick={handleRebootModem}
                disabled={modemRebooting}
              >
                {modemRebooting ? '⏳ Reiniciando...' : '🔄 Reiniciar Módem'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ModemView
