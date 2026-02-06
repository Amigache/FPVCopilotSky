import './VideoView.css'
import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useWebSocket } from '../../contexts/WebSocketContext'
import { useToast } from '../../contexts/ToastContext'
import api from '../../services/api'
import { PeerSelector } from '../PeerSelector/PeerSelector'

const VideoView = () => {
  const { t } = useTranslation()
  const { messages } = useWebSocket()
  const { showToast } = useToast()
  
  // State
  const [loading, setLoading] = useState(true)
  const [cameras, setCameras] = useState([])
  const [config, setConfig] = useState({
    device: '/dev/video0',
    codec: 'mjpeg',
    width: 960,
    height: 720,
    framerate: 30,
    quality: 85,
    h264_bitrate: 2000,
    udp_host: '192.168.1.136',
    udp_port: 5600,
    auto_start: false
  })
  const [actionLoading, setActionLoading] = useState(null)
  const [copySuccess, setCopySuccess] = useState(false)
  
  // Track if user has unsaved changes
  const [hasChanges, setHasChanges] = useState(false)
  const initialLoadDone = useRef(false)

  // Get video status from WebSocket
  const status = messages.video_status || {
    available: false,
    streaming: false,
    enabled: true,
    config: {},
    stats: {},
    last_error: null,
    pipeline_string: ''
  }

  // Update local config from WebSocket only on initial load or when no pending changes
  useEffect(() => {
    if (messages.video_status?.config && !hasChanges) {
      setConfig(prev => ({ ...prev, ...messages.video_status.config }))
      initialLoadDone.current = true
    }
  }, [messages.video_status, hasChanges])
  
  // Wrapper to track changes
  const updateConfig = (updater) => {
    setConfig(updater)
    if (initialLoadDone.current) {
      setHasChanges(true)
    }
  }

  // Load cameras only once (they don't change frequently)
  const loadCameras = useCallback(async () => {
    try {
      const response = await api.get('/api/video/cameras')
      if (response.ok) {
        const data = await response.json()
        setCameras(data.cameras || [])
      }
    } catch (error) {
      console.error('Error loading cameras:', error)
    }
  }, [])

  // Initial load - cameras only, status comes via WebSocket
  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      await loadCameras()
      setLoading(false)
    }
    loadData()
  }, [loadCameras])

  // Actions - Apply config before starting
  const applyConfigAndStart = async () => {
    setActionLoading('start')
    try {
      // First apply video config
      await api.post('/api/video/config/video', {
        device: config.device,
        width: parseInt(config.width),
        height: parseInt(config.height),
        framerate: parseInt(config.framerate),
        codec: config.codec,
        quality: parseInt(config.quality),
        h264_bitrate: parseInt(config.h264_bitrate)
      })
      
      // Then start
      const response = await api.post('/api/video/start')
      const data = await response.json()
      if (data.success) {
        showToast(t('views.video.streamStarted'), 'success')
      } else {
        showToast(data.message || t('views.video.errorStarting'), 'error')
      }
    } catch (error) {
      showToast(error.message || t('views.video.errorStarting'), 'error')
    }
    setActionLoading(null)
  }

  const stopStream = async () => {
    setActionLoading('stop')
    try {
      const response = await api.post('/api/video/stop')
      const data = await response.json()
      if (data.success) {
        showToast(t('views.video.streamStopped'), 'success')
      } else {
        showToast(data.message || t('views.video.errorStopping'), 'error')
      }
    } catch (error) {
      showToast(error.message || t('views.video.errorStopping'), 'error')
    }
    setActionLoading(null)
  }

  const restartStream = async () => {
    setActionLoading('restart')
    try {
      // Apply config first, then restart
      await api.post('/api/video/config/video', {
        device: config.device,
        width: parseInt(config.width),
        height: parseInt(config.height),
        framerate: parseInt(config.framerate),
        codec: config.codec,
        quality: parseInt(config.quality),
        h264_bitrate: parseInt(config.h264_bitrate)
      })
      
      const response = await api.post('/api/video/restart')
      const data = await response.json()
      if (data.success) {
        showToast(t('views.video.streamRestarted'), 'success')
      } else {
        showToast(data.message || t('views.video.errorRestarting'), 'error')
      }
    } catch (error) {
      showToast(error.message || t('views.video.errorRestarting'), 'error')
    }
    setActionLoading(null)
  }

  const applySettings = async () => {
    setActionLoading('apply')
    try {
      // Apply video config
      const videoRes = await api.post('/api/video/config/video', {
        device: config.device,
        width: parseInt(config.width),
        height: parseInt(config.height),
        framerate: parseInt(config.framerate),
        codec: config.codec,
        quality: parseInt(config.quality),
        h264_bitrate: parseInt(config.h264_bitrate)
      })
      
      // Apply streaming config (including auto_start)
      const streamRes = await api.post('/api/video/config/streaming', {
        udp_host: config.udp_host,
        udp_port: parseInt(config.udp_port),
        auto_start: config.auto_start
      })

      const videoData = await videoRes.json()
      const streamData = await streamRes.json()

      if (videoData.success && streamData.success) {
        setHasChanges(false)  // Reset changes flag after successful save
        
        // If currently streaming, restart to apply changes
        if (status.streaming) {
          const restartRes = await api.post('/api/video/restart')
          const restartData = await restartRes.json()
          if (restartData.success) {
            showToast(t('views.video.configAppliedAndRestarted'), 'success')
          } else {
            showToast(t('views.video.configSavedRestartError'), 'warning')
          }
        } else {
          showToast(t('views.video.configAppliedAndSaved'), 'success')
        }
      } else {
        showToast(videoData.message || streamData.message || 'Error', 'error')
      }
    } catch (error) {
      showToast(error.message || t('views.video.errorApplying'), 'error')
    }
    setActionLoading(null)
  }

  const copyPipeline = async () => {
    const pipeline = getPipelineString()
    
    try {
      // Try modern clipboard API first (requires HTTPS)
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(pipeline)
      } else {
        // Fallback for HTTP: use execCommand
        const textarea = document.createElement('textarea')
        textarea.value = pipeline
        textarea.style.position = 'fixed'
        textarea.style.opacity = '0'
        document.body.appendChild(textarea)
        textarea.select()
        document.execCommand('copy')
        document.body.removeChild(textarea)
      }
      
      setCopySuccess(true)
      showToast(t('views.video.pipelineCopied'), 'success')
      setTimeout(() => setCopySuccess(false), 2000)
    } catch (error) {
      showToast(t('views.video.errorCopying'), 'error')
    }
  }

  // Get pipeline based on codec
  const getPipelineString = () => {
    if (config.codec === 'h264') {
      return `udpsrc port=${config.udp_port} caps="application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)H264, payload=(int)96" ! rtph264depay ! avdec_h264 ! videoconvert ! video/x-raw,format=BGRA ! appsink name=outsink sync=false`
    }
    return `udpsrc port=${config.udp_port} caps="application/x-rtp, media=(string)video, clock-rate=(int)90000, encoding-name=(string)JPEG, payload=(int)26" ! rtpjpegdepay ! jpegdec ! videoconvert ! video/x-raw,format=BGRA ! appsink name=outsink sync=false`
  }

  // Get current camera info - fallback to first available if configured device not found
  const currentCamera = cameras.find(cam => cam.device === config.device) || cameras[0]
  
  // Auto-select first camera if configured device doesn't exist
  useEffect(() => {
    if (cameras.length > 0 && !cameras.find(cam => cam.device === config.device)) {
      const firstCam = cameras[0]
      if (firstCam.resolutions && firstCam.resolutions.length > 0) {
        const firstRes = firstCam.resolutions[0]
        const [w, h] = firstRes.split('x')
        const fps = firstCam.resolutions_fps?.[firstRes]?.[0] || 30
        setConfig(prev => ({
          ...prev,
          device: firstCam.device,
          width: parseInt(w),
          height: parseInt(h),
          framerate: fps
        }))
      }
    }
  }, [cameras, config.device])
  
  // Get available resolutions for current camera
  const availableResolutions = currentCamera?.resolutions || []
  
  // Get available FPS for current resolution
  const currentResolution = `${config.width}x${config.height}`
  const availableFps = currentCamera?.resolutions_fps?.[currentResolution] || [30, 24, 15]

  // Handle camera change - reset to first available resolution
  const handleCameraChange = (device) => {
    const camera = cameras.find(cam => cam.device === device)
    if (camera && camera.resolutions && camera.resolutions.length > 0) {
      const firstRes = camera.resolutions[0]
      const [w, h] = firstRes.split('x')
      const fps = camera.resolutions_fps?.[firstRes]?.[0] || 30
      updateConfig(prev => ({
        ...prev,
        device,
        width: parseInt(w),
        height: parseInt(h),
        framerate: fps
      }))
    } else {
      updateConfig(prev => ({ ...prev, device }))
    }
  }

  // Handle resolution change - reset to first available FPS
  const handleResolutionChange = (resolution) => {
    const [w, h] = resolution.split('x')
    const fps = currentCamera?.resolutions_fps?.[resolution]?.[0] || 30
    updateConfig(prev => ({
      ...prev,
      width: parseInt(w),
      height: parseInt(h),
      framerate: fps
    }))
  }

  if (loading) {
    return (
      <div className="card">
        <h2>{t('views.video.title')}</h2>
        <div className="waiting-data">
          <div className="spinner-small"></div>
          {t('common.loadingContent', 'Cargando contenido')}
        </div>
      </div>
    )
  }

  if (!status.available) {
    return (
      <div className="card">
        <h2>{t('views.video.title')}</h2>
        <div className="error-box">
          {t('views.video.gstreamerNotAvailable')}
        </div>
      </div>
    )
  }

  return (
    <div className="video-view">
      {/* Status Banner */}
      <div className={`status-banner ${status.streaming ? 'streaming' : 'stopped'}`}>
        <div className="status-indicator">
          <span className={`status-dot ${status.streaming ? 'live' : ''}`}></span>
          <span className="status-text">
            {status.streaming ? t('views.video.streaming') : t('views.video.stopped')}
          </span>
        </div>
        {status.streaming && (
          <div className="status-info">
            {config.codec.toUpperCase()} • {config.width}x{config.height} • {config.udp_host}:{config.udp_port}
          </div>
        )}
        {status.last_error && (
          <div className="status-error">❌ {status.last_error}</div>
        )}
      </div>

      <div className="video-columns">
        {/* Left Column - Video Settings */}
        <div className="video-col">
          <div className="card">
            <h2>{t('views.video.videoConfiguration')}</h2>
            
            <div className="form-group">
              <label>{t('views.video.codec')}</label>
              <select 
                value={config.codec} 
                onChange={(e) => updateConfig(prev => ({ ...prev, codec: e.target.value }))}
              >
                <option value="mjpeg">{t('views.video.codecMjpeg')}</option>
                <option value="h264">{t('views.video.codecH264')}</option>
              </select>
            </div>

            <div className="form-group">
              <label>{t('views.video.videoSource')}</label>
              <select 
                value={config.device} 
                onChange={(e) => handleCameraChange(e.target.value)}
              >
                {cameras.length === 0 ? (
                  <option value="">{t('views.video.noCamerasAvailable')}</option>
                ) : (
                  cameras.map(cam => (
                    <option key={cam.device} value={cam.device}>
                      {cam.name} ({cam.device})
                    </option>
                  ))
                )}
              </select>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>{t('views.video.resolution')}</label>
                <select 
                  value={`${config.width}x${config.height}`}
                  onChange={(e) => handleResolutionChange(e.target.value)}
                >
                  {availableResolutions.length > 0 ? (
                    availableResolutions.map(res => (
                      <option key={res} value={res}>{res}</option>
                    ))
                  ) : (
                    <option value={`${config.width}x${config.height}`}>
                      {config.width}x{config.height}
                    </option>
                  )}
                </select>
              </div>

              <div className="form-group">
                <label>{t('views.video.fps')}</label>
                <select 
                  value={config.framerate}
                  onChange={(e) => updateConfig(prev => ({ ...prev, framerate: parseInt(e.target.value) }))}
                >
                  {availableFps.map(fps => (
                    <option key={fps} value={fps}>{fps} fps</option>
                  ))}
                </select>
              </div>
            </div>

            {/* MJPEG Settings */}
            {config.codec === 'mjpeg' && (
              <div className="form-group">
                <label>{t('views.video.jpegQuality')}: {config.quality}</label>
                <input 
                  type="range" 
                  min="50" 
                  max="100" 
                  value={config.quality}
                  onChange={(e) => updateConfig(prev => ({ ...prev, quality: parseInt(e.target.value) }))}
                  className="slider"
                />
              </div>
            )}

            {/* H.264 Settings */}
            {config.codec === 'h264' && (
              <div className="form-group">
                <label>{t('views.video.bitrate')}</label>
                <select 
                  value={config.h264_bitrate}
                  onChange={(e) => updateConfig(prev => ({ ...prev, h264_bitrate: parseInt(e.target.value) }))}
                >
                  <option value="500">500 ({t('views.video.bitrateMobile')})</option>
                  <option value="1000">1000</option>
                  <option value="2000">2000 ({t('views.video.bitrateRecommended')})</option>
                  <option value="3000">3000</option>
                  <option value="5000">5000 ({t('views.video.bitrateWifi')})</option>
                </select>
              </div>
            )}
          </div>

          {/* Network Settings */}
          <div className="card">
            <h2>{t('views.video.networkUdpRtp')}</h2>
            <div className="form-row">
              <div className="form-group">
                <PeerSelector
                  label={t('views.video.destinationIp')}
                  value={config.udp_host}
                  onChange={(value) => updateConfig(prev => ({ ...prev, udp_host: value }))}
                  placeholder="192.168.1.100"
                />
              </div>
              <div className="form-group">
                <label>{t('views.video.udpPort')}</label>
                <input 
                  type="number" 
                  value={config.udp_port}
                  min="1024"
                  max="65535"
                  onChange={(e) => updateConfig(prev => ({ ...prev, udp_port: parseInt(e.target.value) }))}
                />
              </div>
            </div>
            
            <div className="form-group auto-start-toggle">
              <label className="toggle-label">
                <input 
                  type="checkbox" 
                  checked={config.auto_start || false}
                  onChange={(e) => updateConfig(prev => ({ ...prev, auto_start: e.target.checked }))}
                />
                <span className="toggle-switch"></span>
                <span className="toggle-text">{t('views.video.autoStart')}</span>
              </label>
            </div>
          </div>
        </div>

        {/* Right Column - Controls & Pipeline */}
        <div className="video-col">
          {/* Stream Control */}
          <div className="card">
            <h2>{t('views.video.streamControl')}</h2>
            <div className="button-group">
              <button 
                className="btn btn-apply"
                onClick={applySettings}
                disabled={actionLoading !== null}
              >
                {actionLoading === 'apply' ? '⏳' : t('views.video.apply')}
              </button>
              <button 
                className="btn btn-restart"
                onClick={restartStream}
                disabled={actionLoading !== null}
              >
                {actionLoading === 'restart' ? '⏳' : t('views.video.restart')}
              </button>
            </div>
            <div className="button-group" style={{ marginTop: '10px' }}>
              <button 
                className="btn btn-start"
                onClick={applyConfigAndStart}
                disabled={actionLoading !== null || status.streaming}
              >
                {actionLoading === 'start' ? '⏳' : t('views.video.start')}
              </button>
              <button 
                className="btn btn-stop"
                onClick={stopStream}
                disabled={actionLoading !== null || !status.streaming}
              >
                {actionLoading === 'stop' ? '⏳' : t('views.video.stop')}
              </button>
            </div>
          </div>

          {/* GStreamer Pipeline */}
          <div className="card">
            <h2>{t('views.video.pipelineTitle')}</h2>
            <div className="info-box">
              {t('views.video.pipelineInstructions')}
            </div>
            <div className="pipeline-box">
              <code>{getPipelineString()}</code>
            </div>
            <button 
              className={`btn btn-copy ${copySuccess ? 'success' : ''}`}
              onClick={copyPipeline}
            >
              {copySuccess ? t('views.video.copied') : t('views.video.copyToClipboard')}
            </button>
          </div>

          {/* Stats */}
          {status.streaming && status.stats && (
            <div className="card">
              <h2>{t('views.video.statistics')}</h2>
              <div className="stats-grid">
                <div className="stat-item">
                  <span className="stat-label">{t('views.video.uptime')}</span>
                  <span className="stat-value">
                    {status.stats.uptime ? `${Math.floor(status.stats.uptime)}s` : '-'}
                  </span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">{t('views.video.errors')}</span>
                  <span className="stat-value">{status.stats.errors || 0}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default VideoView
