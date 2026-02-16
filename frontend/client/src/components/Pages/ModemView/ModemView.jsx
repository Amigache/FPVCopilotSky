import './ModemView.css'
import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../../../contexts/ToastContext'
import { useModal } from '../../../contexts/ModalContext'
import { useWebSocket } from '../../../contexts/WebSocketContext'
import api from '../../../services/api'
import { MODEM_API_TIMEOUTS, REBOOT_CONFIG } from './modemConstants'

const ModemView = () => {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { showModal } = useModal()
  const { messages: wsMessages } = useWebSocket()

  // State
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState(null)
  const [bandPresets, setBandPresets] = useState(null)
  const [videoQuality, setVideoQuality] = useState(null)
  const [latency, setLatency] = useState(null)

  // Loading states
  const [changingBand, setChangingBand] = useState(false)
  const [changingMode, setChangingMode] = useState(false)
  const [togglingVideoMode, setTogglingVideoMode] = useState(false)
  const [testingLatency, setTestingLatency] = useState(false)
  const [modemRebooting, setModemRebooting] = useState(false)

  // Load modem status
  const loadStatus = useCallback(async () => {
    try {
      const response = await api.get(
        '/api/modem/status/enhanced/huawei_e3372h',
        MODEM_API_TIMEOUTS.STATUS_ENHANCED
      )
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
      const response = await api.get('/api/modem/band/presets/huawei_e3372h')
      if (response.ok) {
        const data = await response.json()
        setBandPresets(data)
      }
    } catch (error) {
      console.error('Error loading band presets:', error)
    }
  }, [])

  // Test latency
  const handleTestLatency = async () => {
    setTestingLatency(true)
    try {
      const response = await api.get('/api/modem/latency/huawei_e3372h')
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

  // Initial load (one-time HTTP for first paint, then WS takes over)
  useEffect(() => {
    const loadAll = async () => {
      setLoading(true)
      await Promise.all([loadStatus(), loadBandPresets()])
      setLoading(false)
      // Auto-test latency on first load
      handleTestLatency()
    }
    loadAll()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadStatus, loadBandPresets])

  // WebSocket: update modem data from server push (replaces polling)
  useEffect(() => {
    if (wsMessages?.modem_status) {
      const data = wsMessages.modem_status
      setStatus(data)
      if (data.video_quality) setVideoQuality(data.video_quality)
    }
  }, [wsMessages?.modem_status])

  // Set LTE band
  const handleSetBand = async (preset) => {
    setChangingBand(true)
    showToast(`⏳ ${t('modem.changingBand')}`, 'info')
    try {
      const response = await api.post(
        '/api/modem/band/huawei_e3372h',
        { preset },
        MODEM_API_TIMEOUTS.BAND_CHANGE
      )
      if (response.ok) {
        const data = await response.json()
        showToast(`✅ ${t('modem.bandChanged', { name: data.preset_name })}`, 'success')
        await loadStatus()
      } else {
        const data = await response.json()
        showToast(data.detail || t('modem.errorChangingBand'), 'error')
      }
    } catch (error) {
      showToast(error.message, 'error')
    }
    setChangingBand(false)
  }

  // Set network mode
  const handleSetNetworkMode = async (mode) => {
    setChangingMode(true)
    showToast(`⏳ ${t('modem.changingNetworkMode')}`, 'info')
    try {
      const response = await api.post(
        '/api/modem/mode/huawei_e3372h',
        { mode },
        MODEM_API_TIMEOUTS.MODE_CHANGE
      )
      if (response.ok) {
        showToast(`✅ ${t('modem.networkModeChanged')}`, 'success')
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
        ? '/api/modem/video-mode/disable/huawei_e3372h'
        : '/api/modem/video-mode/enable/huawei_e3372h'

      const response = await api.post(endpoint, {}, MODEM_API_TIMEOUTS.VIDEO_MODE_TOGGLE)
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

  // Reboot modem
  const handleRebootModem = () => {
    showModal({
      title: t('modem.rebootModem'),
      message: t('modem.confirmRebootModem'),
      type: 'confirm',
      confirmText: t('common.save'),
      cancelText: t('common.cancel'),
      onConfirm: async () => {
        try {
          setModemRebooting(true)
          const response = await api.post('/api/modem/reboot/huawei_e3372h')
          if (response.ok) {
            showToast(`⏳ ${t('network.modemRebooting')}`, 'info')

            // Poll for modem to come back online (check every 5s for up to 60s)
            let attempts = 0
            const maxAttempts = REBOOT_CONFIG.MAX_ATTEMPTS
            const checkModem = async () => {
              attempts++
              try {
                const checkResponse = await api.get(
                  '/api/modem/status/huawei_e3372h',
                  MODEM_API_TIMEOUTS.STATUS_CHECK
                )
                if (checkResponse.ok) {
                  const data = await checkResponse.json()
                  if (data.available) {
                    setModemRebooting(false)
                    showToast(`✅ ${t('modem.modemOnline')}`, 'success')
                    await loadStatus()
                    return
                  }
                }
              } catch (_e) {
                // Expected during reboot
              }

              if (attempts < maxAttempts) {
                setTimeout(checkModem, 5000)
              } else {
                setModemRebooting(false)
                showToast(`⚠️ ${t('modem.modemNoResponse')}`, 'warning')
              }
            }

            // Start checking after initial delay
            setTimeout(checkModem, REBOOT_CONFIG.CHECK_INTERVAL)
          } else {
            setModemRebooting(false)
            const data = await response.json()
            showToast(data.detail || 'Error', 'error')
          }
        } catch (error) {
          setModemRebooting(false)
          showToast(error.message, 'error')
        }
      },
    })
  }

  // Get quality color class
  const getQualityColorClass = (level) => {
    switch (level) {
      case 'excellent':
        return 'quality-excellent'
      case 'good':
        return 'quality-good'
      case 'moderate':
        return 'quality-moderate'
      case 'poor':
        return 'quality-poor'
      case 'critical':
        return 'quality-critical'
      default:
        return 'quality-unknown'
    }
  }

  if (loading) {
    return (
      <div className="card">
        <h2>📶 {t('modem.title')}</h2>
        <div className="waiting-data">
          <div className="spinner-small"></div>
          {t('common.loadingContent')}
        </div>
      </div>
    )
  }

  if (!status?.available) {
    return (
      <div className="modem-view">
        <div className="card modem-offline">
          <h2>📶 {t('modem.title')}</h2>
          <div className="offline-message">
            <span className="offline-icon">❌</span>
            <p>{t('modem.notDetected')}</p>
            <p className="offline-hint">{t('modem.checkConnection')}</p>
            <button className="btn-primary" onClick={loadStatus}>
              🔄 {t('modem.retry')}
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
              {status.video_mode_active ? t('modem.videoModeActive') : t('modem.normalMode')}
            </span>
            <span className="banner-description">
              {status.video_mode_active ? t('modem.videoModeDesc') : t('modem.normalModeDesc')}
            </span>
          </div>
        </div>
        <button
          className={`btn-video-mode ${status.video_mode_active ? 'active' : ''}`}
          onClick={handleToggleVideoMode}
          disabled={togglingVideoMode}
        >
          {togglingVideoMode
            ? '⏳'
            : status.video_mode_active
              ? `⏹️ ${t('modem.deactivate')}`
              : `🎬 ${t('modem.activateVideoMode')}`}
        </button>
      </div>

      <div className="modem-sections">
        {/* === CARD 1: INFO - Información del Dispositivo === */}
        <div className="card info-card">
          <h2>📡 {t('modem.information')}</h2>
          <div className="operator-main-info">
            <span className="operator-name">{network.operator || t('modem.unknown')}</span>
            <span className="tech-badge">
              {network.network_type_ex || network.network_type || '-'}
            </span>
            <span
              className={`connection-badge ${
                network.connection_status === 'Connected' ? 'connected' : 'disconnected'
              }`}
            >
              {network.connection_status === 'Connected'
                ? `● ${t('network.connected')}`
                : `○ ${t('modem.disconnected')}`}
            </span>
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
              <span className="info-label">{t('modem.roaming')}</span>
              <span className={`info-value ${network.roaming ? 'warning' : ''}`}>
                {network.roaming ? `⚠️ ${t('modem.roamingActive')}` : t('modem.roamingNo')}
              </span>
            </div>
            <div className="info-item">
              <span className="info-label">{t('modem.signal')}</span>
              <span className="info-value">{'📶'.repeat(network.signal_icon || 0)}</span>
            </div>
            <div className="info-item">
              <span className="info-label">{t('modem.model')}</span>
              <span className="info-value">{device.device_name || '-'}</span>
            </div>
            <div className="info-item">
              <span className="info-label">IMEI</span>
              <span className="info-value mono small">{device.imei || '-'}</span>
            </div>
            <div className="info-item">
              <span className="info-label">{t('modem.hardware')}</span>
              <span className="info-value">{device.hardware_version || '-'}</span>
            </div>
            <div className="info-item">
              <span className="info-label">{t('modem.firmware')}</span>
              <span className="info-value">{device.software_version || '-'}</span>
            </div>
          </div>
        </div>

        {/* === CARD 2: KPIs - Calidad, Latencia, Señal, Tráfico === */}
        <div className="card kpi-card">
          <h2>📊 {t('modem.performanceMetrics')}</h2>

          <div className="kpi-sections">
            {/* Video Quality Section */}
            <div className="kpi-section">
              <div className="kpi-header">
                <span className="kpi-title">🎬 {t('modem.videoQuality')}</span>
              </div>
              {videoQuality?.available ? (
                <div className="kpi-content">
                  <div className={`quality-badge ${getQualityColorClass(videoQuality.quality)}`}>
                    <span className="quality-text">{videoQuality.label}</span>
                    <span className="quality-bitrate">{videoQuality.max_bitrate_kbps} kbps</span>
                  </div>
                  <div className="quality-rec">
                    {t('modem.resolution')}: <strong>{videoQuality.recommended_resolution}</strong>
                  </div>
                  {videoQuality.warnings?.length > 0 && (
                    <div className="quality-warnings">
                      {videoQuality.warnings.map((w, i) => (
                        <span key={i} className="warning-tag">
                          ⚠️ {w}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <div className="kpi-no-data">{t('modem.noData')}</div>
              )}
            </div>

            {/* Latency Section */}
            <div className="kpi-section">
              <div className="kpi-header">
                <span className="kpi-title">⏱️ {t('modem.latency')}</span>
                <button className="btn-mini" onClick={handleTestLatency} disabled={testingLatency}>
                  {testingLatency ? '...' : '🔄'}
                </button>
              </div>
              {testingLatency && !latency?.success ? (
                <div className="kpi-no-data">
                  <div className="spinner-small"></div>
                  {t('modem.testing')}...
                </div>
              ) : latency?.success ? (
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
                <div className="kpi-no-data">{t('modem.noData')}</div>
              )}
            </div>

            {/* Signal Section */}
            <div className="kpi-section signal-section">
              <div className="kpi-header">
                <span className="kpi-title">📶 {t('modem.lteSignal')}</span>
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
                <span className="kpi-title">📈 {t('modem.traffic')}</span>
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
                  {t('modem.total')}: ⬇️ {traffic.total_download || '-'} / ⬆️{' '}
                  {traffic.total_upload || '-'}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* === CARD 3: CONFIGURACIÓN - Banda, Modo, Sesión === */}
        <div className="card config-card">
          <h2>⚙️ {t('modem.configuration')}</h2>

          <div className="config-sections">
            {/* Band Config */}
            <div className="config-section">
              <div className="config-header">
                <span className="config-title">📡 {t('modem.lteBand')}</span>
              </div>

              {changingBand && <div className="config-loading">⏳ {t('modem.applying')}</div>}

              <div className="band-info">
                <span className="band-enabled">
                  {t('modem.enabled')}:{' '}
                  <strong>
                    {currentBand.enabled_bands?.length > 0
                      ? currentBand.enabled_bands.join(', ')
                      : t('modem.all')}
                  </strong>
                </span>
              </div>

              <div className="preset-grid">
                {bandPresets?.presets &&
                  Object.entries(bandPresets.presets).map(([key, preset]) => (
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
                <span className="config-title">📶 {t('modem.networkMode')}</span>
              </div>

              {changingMode && <div className="config-loading">⏳ {t('modem.changing')}</div>}

              <div className="current-mode-info">
                {t('modem.current')}:{' '}
                <strong>{status.mode?.network_mode_name || network.network_type || '-'}</strong>
              </div>

              <div className="mode-grid">
                <button
                  className={`btn-mode-compact ${
                    status.mode?.network_mode === '00' ? 'active' : ''
                  }`}
                  onClick={() => handleSetNetworkMode('00')}
                  disabled={changingMode}
                >
                  Auto
                </button>
                <button
                  className={`btn-mode-compact ${
                    status.mode?.network_mode === '03' ? 'active' : ''
                  }`}
                  onClick={() => handleSetNetworkMode('03')}
                  disabled={changingMode}
                >
                  4G Only
                </button>
                <button
                  className={`btn-mode-compact ${
                    status.mode?.network_mode === '02' ? 'active' : ''
                  }`}
                  onClick={() => handleSetNetworkMode('02')}
                  disabled={changingMode}
                >
                  3G Only
                </button>
              </div>
            </div>
          </div>

          {/* Reboot Section */}
          <div className="config-group reboot-section">
            <h3>🔄 {t('modem.rebootSection')}</h3>
            <div className="reboot-container">
              <span className="reboot-hint">{t('modem.rebootHint')}</span>
              <button className="btn-reboot" onClick={handleRebootModem} disabled={modemRebooting}>
                {modemRebooting ? `⏳ ${t('modem.rebooting')}` : `🔄 ${t('modem.rebootModem')}`}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ModemView
