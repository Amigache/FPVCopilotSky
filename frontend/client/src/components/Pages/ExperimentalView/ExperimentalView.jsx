import './ExperimentalView.css'
import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../../../contexts/ToastContext'
import { useWebSocket } from '../../../contexts/WebSocketContext'
import Toggle from '../../Toggle/Toggle'
import api from '../../../services/api'

const ExperimentalView = () => {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { messages } = useWebSocket()

  const [opencvEnabled, setOpencvEnabled] = useState(false)
  const [loading, setLoading] = useState(true)
  const [applying, setApplying] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const applyTimeoutRef = useRef(null)

  // OpenCV configuration
  const [config, setConfig] = useState({
    filter: 'none',
    osd_enabled: false,
    edgeThreshold1: 100,
    edgeThreshold2: 200,
    blurKernel: 15,
    thresholdValue: 127,
  })

  const filters = [
    { id: 'none', name: t('experimental.opencv.filters.none') },
    { id: 'edges', name: t('experimental.opencv.filters.edges') },
    { id: 'blur', name: t('experimental.opencv.filters.blur') },
    { id: 'grayscale', name: t('experimental.opencv.filters.grayscale') },
    { id: 'threshold', name: t('experimental.opencv.filters.threshold') },
    { id: 'contours', name: t('experimental.opencv.filters.contours') },
  ]

  // Load current configuration
  useEffect(() => {
    loadConfig()

    // Cleanup timeout on unmount
    return () => {
      if (applyTimeoutRef.current) {
        clearTimeout(applyTimeoutRef.current)
      }
    }
  }, [])

  // Update from WebSocket
  useEffect(() => {
    if (messages.experimental) {
      const data = messages.experimental
      setOpencvEnabled(data.opencv_enabled || false)
      if (data.config) {
        setConfig((prev) => ({ ...prev, ...data.config }))
      }
    }
  }, [messages.experimental])

  const loadConfig = async () => {
    try {
      const response = await api.get('/api/experimental/config')
      if (response.ok) {
        const data = await response.json()
        setOpencvEnabled(data.opencv_enabled || false)
        if (data.config) {
          setConfig((prev) => ({ ...prev, ...data.config }))
        }
      }
    } catch (error) {
      console.error('Error loading config:', error)
    } finally {
      setLoading(false)
    }
  }

  // Restart video stream to apply changes
  const restartVideoStream = useCallback(async () => {
    try {
      setRestarting(true)
      const response = await api.post('/api/video/restart')
      if (response.ok) {
        // Don't show toast, changes are already applied
      } else {
        console.error('Error restarting video stream')
      }
    } catch (error) {
      console.error('Error restarting video stream:', error)
    } finally {
      setRestarting(false)
    }
  }, [])

  const handleToggleOpenCV = async (event) => {
    const enabled = event.target.checked
    setApplying(true)
    try {
      const response = await api.post('/api/experimental/toggle', {
        enabled,
      })

      if (response.ok) {
        const data = await response.json()
        setOpencvEnabled(data.opencv_enabled)
        showToast(
          enabled ? t('experimental.success.enabled') : t('experimental.success.disabled'),
          'success'
        )
        // Restart video stream to apply OpenCV changes
        await restartVideoStream()
      } else {
        const data = await response.json()
        showToast(data.message || t('experimental.error.toggle'), 'error')
      }
    } catch (error) {
      console.error('Error toggling OpenCV:', error)
      showToast(t('experimental.error.toggle'), 'error')
    } finally {
      setApplying(false)
    }
  }

  // Auto-apply config with debounce and optional restart
  const applyConfigAuto = useCallback(
    async (newConfig, immediate = false, shouldRestart = false) => {
      // Clear any pending timeout
      if (applyTimeoutRef.current) {
        clearTimeout(applyTimeoutRef.current)
      }

      const applyNow = async () => {
        try {
          const response = await api.post('/api/experimental/config', newConfig)
          if (!response.ok) {
            const data = await response.json()
            console.error('Error applying config:', data.message)
          } else if (shouldRestart) {
            // Restart video stream to apply changes
            await restartVideoStream()
          }
        } catch (error) {
          console.error('Error applying config:', error)
        }
      }

      if (immediate) {
        await applyNow()
      } else {
        // Debounce for sliders (wait 800ms after last change)
        applyTimeoutRef.current = setTimeout(applyNow, 800)
      }
    },
    [restartVideoStream]
  )

  const handleToggleOSD = async (event) => {
    const osdEnabled = event.target.checked
    const newConfig = { ...config, osd_enabled: osdEnabled }
    setConfig(newConfig)
    try {
      const response = await api.post('/api/experimental/config', newConfig)
      if (response.ok) {
        showToast(
          osdEnabled
            ? t('experimental.success.configApplied')
            : t('experimental.success.configApplied'),
          'success'
        )
        // Restart video stream to apply OSD changes
        await restartVideoStream()
      }
    } catch (error) {
      console.error('Error toggling OSD:', error)
      setConfig((prev) => ({ ...prev, osd_enabled: !osdEnabled }))
    }
  }

  if (loading) {
    return (
      <div className="experimental-view">
        <div className="waiting-data">
          <div className="spinner-small"></div>
          <span>{t('common.loading')}</span>
        </div>
      </div>
    )
  }

  return (
    <div className="experimental-view">
      <div className="experimental-header">
        <h2>🧪 {t('experimental.title')}</h2>
        <p className="experimental-description">{t('experimental.description')}</p>
      </div>

      <div className="experimental-content">
        {/* OpenCV Configuration Section */}
        <div className="experimental-section">
          <h3>📷 {t('experimental.opencv.title')}</h3>
          <p className="section-description">{t('experimental.opencv.description')}</p>

          {/* Status */}
          <div className={`opencv-status ${opencvEnabled ? 'active' : ''}`}>
            <div className="opencv-status-label">
              <span className={`status-indicator ${opencvEnabled ? 'active' : ''}`}></span>
              <span>
                {opencvEnabled
                  ? t('experimental.opencv.active')
                  : t('experimental.opencv.inactive')}
              </span>
            </div>
            <Toggle
              checked={opencvEnabled}
              onChange={handleToggleOpenCV}
              disabled={applying || restarting}
            />
          </div>

          {/* Info box */}
          <div className="info-box warning">
            <p>{t('experimental.opencv.warning')}</p>
          </div>

          {/* OSD Toggle */}
          <div className="control-group">
            <label className="control-label">{t('experimental.opencv.osdEnabled')}</label>
            <div className="control-toggle-inline">
              <Toggle
                checked={config.osd_enabled}
                onChange={handleToggleOSD}
                disabled={!opencvEnabled || applying || restarting}
              />
              <span className="toggle-description">{t('experimental.opencv.osdDescription')}</span>
            </div>
          </div>

          {/* Filter selection */}
          <div className="control-group">
            <label className="control-label">{t('experimental.opencv.selectFilter')}</label>
            <select
              value={config.filter}
              onChange={(e) => {
                const newConfig = { ...config, filter: e.target.value }
                setConfig(newConfig)
                applyConfigAuto(newConfig, true, true)
              }}
              className="control-select"
              disabled={!opencvEnabled || applying || restarting}
            >
              {filters.map((filter) => (
                <option key={filter.id} value={filter.id}>
                  {filter.name}
                </option>
              ))}
            </select>
          </div>

          {/* Filter-specific parameters */}
          {config.filter === 'edges' && (
            <>
              <div className="control-group">
                <label className="control-label">
                  {t('experimental.opencv.edgeThreshold1')}
                  <span className="slider-value">{config.edgeThreshold1}</span>
                </label>
                <input
                  type="range"
                  min="0"
                  max="255"
                  value={config.edgeThreshold1}
                  onChange={(e) => {
                    const newConfig = { ...config, edgeThreshold1: parseInt(e.target.value) }
                    setConfig(newConfig)
                    applyConfigAuto(newConfig)
                  }}
                  className="control-slider"
                  disabled={!opencvEnabled || applying}
                />
              </div>
              <div className="control-group">
                <label className="control-label">
                  {t('experimental.opencv.edgeThreshold2')}
                  <span className="slider-value">{config.edgeThreshold2}</span>
                </label>
                <input
                  type="range"
                  min="0"
                  max="255"
                  value={config.edgeThreshold2}
                  onChange={(e) => {
                    const newConfig = { ...config, edgeThreshold2: parseInt(e.target.value) }
                    setConfig(newConfig)
                    applyConfigAuto(newConfig)
                  }}
                  className="control-slider"
                  disabled={!opencvEnabled || applying}
                />
              </div>
            </>
          )}

          {config.filter === 'blur' && (
            <div className="control-group">
              <label className="control-label">
                {t('experimental.opencv.blurKernel')}
                <span className="slider-value">{config.blurKernel}</span>
              </label>
              <input
                type="range"
                min="3"
                max="31"
                step="2"
                value={config.blurKernel}
                onChange={(e) => {
                  const newConfig = { ...config, blurKernel: parseInt(e.target.value) }
                  setConfig(newConfig)
                  applyConfigAuto(newConfig)
                }}
                className="control-slider"
                disabled={!opencvEnabled || applying}
              />
            </div>
          )}

          {config.filter === 'threshold' && (
            <div className="control-group">
              <label className="control-label">
                {t('experimental.opencv.thresholdValue')}
                <span className="slider-value">{config.thresholdValue}</span>
              </label>
              <input
                type="range"
                min="0"
                max="255"
                value={config.thresholdValue}
                onChange={(e) => {
                  const newConfig = { ...config, thresholdValue: parseInt(e.target.value) }
                  setConfig(newConfig)
                  applyConfigAuto(newConfig)
                }}
                className="control-slider"
                disabled={!opencvEnabled || applying}
              />
            </div>
          )}
        </div>

        {/* Info Section */}
        <div className="experimental-section">
          <h3>ℹ️ {t('experimental.info.title')}</h3>
          <p className="section-description">{t('experimental.info.description')}</p>

          <div className="info-box">
            <p>{t('experimental.info.howItWorks')}</p>
          </div>

          <h4
            style={{
              color: 'var(--color-text-primary)',
              marginTop: '1.5rem',
              marginBottom: '0.75rem',
            }}
          >
            {t('experimental.future.title')}
          </h4>
          <ul className="feature-list">
            <li>🎯 {t('experimental.future.objectDetection')}</li>
            <li>🤖 {t('experimental.future.mlIntegration')}</li>
            <li>📊 {t('experimental.future.videoAnalysis')}</li>
            <li>🔍 {t('experimental.future.featureTracking')}</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

export default ExperimentalView
