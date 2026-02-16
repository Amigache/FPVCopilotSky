import './VideoView.css'
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useWebSocket } from '../../../contexts/WebSocketContext'
import { useToast } from '../../../contexts/ToastContext'
import api from '../../../services/api'
import { VIDEO_DEFAULTS, FALLBACK_FPS, EMPTY_STATUS, TIMING, safeInt } from './videoConstants'
import StatusBanner from './StatusBanner'
import VideoSourceCard from './VideoSourceCard'
import EncodingConfigCard from './EncodingConfigCard'
import NetworkSettingsCard from './NetworkSettingsCard'
import StreamControlCard from './StreamControlCard'
import PipelineCard from './PipelineCard'
import StatsCard from './StatsCard'
import WebRTCViewerCard from './WebRTCViewerCard'

const VideoView = () => {
  const { t } = useTranslation()
  const { messages } = useWebSocket()
  const { showToast } = useToast()

  // ── State ──────────────────────────────────────────────────────────────────
  const [loading, setLoading] = useState(true)
  const [cameras, setCameras] = useState([])
  const [availableCodecs, setAvailableCodecs] = useState([])
  const [config, setConfig] = useState({
    device: VIDEO_DEFAULTS.DEVICE,
    codec: VIDEO_DEFAULTS.CODEC,
    width: VIDEO_DEFAULTS.WIDTH,
    height: VIDEO_DEFAULTS.HEIGHT,
    framerate: VIDEO_DEFAULTS.FRAMERATE,
    quality: VIDEO_DEFAULTS.QUALITY,
    h264_bitrate: VIDEO_DEFAULTS.H264_BITRATE,
    gop_size: VIDEO_DEFAULTS.GOP_SIZE,
    mode: VIDEO_DEFAULTS.MODE,
    udp_host: VIDEO_DEFAULTS.UDP_HOST,
    udp_port: VIDEO_DEFAULTS.UDP_PORT,
    multicast_group: VIDEO_DEFAULTS.MULTICAST_GROUP,
    multicast_port: VIDEO_DEFAULTS.MULTICAST_PORT,
    multicast_ttl: VIDEO_DEFAULTS.MULTICAST_TTL,
    rtsp_enabled: false,
    rtsp_url: VIDEO_DEFAULTS.RTSP_URL,
    rtsp_transport: VIDEO_DEFAULTS.RTSP_TRANSPORT,
    auto_start: false,
  })
  const [actionLoading, setActionLoading] = useState(null)
  const [copySuccess, setCopySuccess] = useState(false)
  const [hasChanges, setHasChanges] = useState(false)
  const [networkIp, setNetworkIp] = useState(null)
  const [webrtcVideoStats, setWebrtcVideoStats] = useState(null)
  const [webrtcKey, setWebrtcKey] = useState(0)
  const [networkValidationErrors, setNetworkValidationErrors] = useState(false)
  const [autoAdaptiveBitrate, setAutoAdaptiveBitrate] = useState(true) // Auto-adaptive by default
  const initialLoadDone = useRef(false)
  const liveUpdateTimer = useRef(null)
  const webrtcViewerRef = useRef(null)

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => clearTimeout(liveUpdateTimer.current)
  }, [])

  // ── Payload builder ────────────────────────────────────────────────────────
  const buildVideoConfigPayload = useCallback(() => {
    const camera = cameras.find((cam) => cam.device === config.device)
    return {
      device: config.device,
      device_name: camera?.name || '',
      device_bus_info: camera?.bus_info || '',
      width: safeInt(config.width, VIDEO_DEFAULTS.WIDTH),
      height: safeInt(config.height, VIDEO_DEFAULTS.HEIGHT),
      framerate: safeInt(config.framerate, VIDEO_DEFAULTS.FRAMERATE),
      codec: config.codec,
      quality: safeInt(config.quality, VIDEO_DEFAULTS.QUALITY),
      h264_bitrate: safeInt(config.h264_bitrate, VIDEO_DEFAULTS.H264_BITRATE),
      gop_size: safeInt(config.gop_size, VIDEO_DEFAULTS.GOP_SIZE),
    }
  }, [cameras, config])

  // ── WebSocket status ───────────────────────────────────────────────────────
  const status = messages.video_status || EMPTY_STATUS
  const webrtcStatus = messages.webrtc_status || null

  // Sync remote config → local when no pending changes
  useEffect(() => {
    if (messages.video_status?.config && !hasChanges) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setConfig((prev) => ({ ...prev, ...messages.video_status.config }))
      initialLoadDone.current = true
    }
  }, [messages.video_status, hasChanges])

  // Track local changes
  const updateConfig = useCallback((updater) => {
    setConfig(updater)
    if (initialLoadDone.current) {
      setHasChanges(true)
    }
  }, [])

  // Handle validation state from NetworkSettingsCard
  const handleNetworkValidation = useCallback((hasErrors) => {
    setNetworkValidationErrors(hasErrors)
  }, [])

  // ── Data loading ───────────────────────────────────────────────────────────
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

  const loadCodecs = useCallback(async () => {
    try {
      const response = await api.get('/api/video/codecs')
      if (response.ok) {
        const data = await response.json()
        setAvailableCodecs(data.codecs || [])
        if (data.codecs.length > 0) {
          setConfig((prev) => {
            const currentCodecAvailable = data.codecs.some((c) => c.id === prev.codec)
            if (!currentCodecAvailable) {
              return { ...prev, codec: data.codecs[0].id }
            }
            return prev
          })
        }
      }
    } catch (error) {
      console.error('Error loading codecs:', error)
    }
  }, [])

  const loadNetworkIp = useCallback(async () => {
    try {
      const response = await api.get('/api/video/network/ip')
      if (response.ok) {
        const data = await response.json()
        setNetworkIp(data)
      }
    } catch (error) {
      console.error('Error loading network IP:', error)
    }
  }, [])

  const loadAutoAdaptiveBitrate = useCallback(async () => {
    try {
      const response = await api.get('/api/video/config/auto-adaptive-bitrate')
      if (response.ok) {
        const data = await response.json()
        setAutoAdaptiveBitrate(data.enabled)
      }
    } catch (error) {
      console.error('Error loading auto-adaptive bitrate:', error)
    }
  }, [])

  // Initial data load
  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      await Promise.all([loadCameras(), loadCodecs(), loadNetworkIp(), loadAutoAdaptiveBitrate()])
      setLoading(false)
    }
    loadData()
  }, [loadCameras, loadCodecs, loadNetworkIp, loadAutoAdaptiveBitrate])

  // RTSP mode: auto-populate URL + reload network IP (merged from two effects)
  useEffect(() => {
    if (config.mode === 'rtsp' && initialLoadDone.current) {
      if (networkIp) {
        const isDefaultUrl = config.rtsp_url === VIDEO_DEFAULTS.RTSP_URL || !config.rtsp_url
        if (isDefaultUrl && networkIp.rtsp_url) {
          // eslint-disable-next-line react-hooks/set-state-in-effect
          updateConfig((prev) => ({ ...prev, rtsp_url: networkIp.rtsp_url }))
        }
      }
      loadNetworkIp()
    }
  }, [config.mode]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Action handlers ────────────────────────────────────────────────────────
  const applyConfigAndStart = async () => {
    setActionLoading('start')
    try {
      await api.post('/api/video/config/video', buildVideoConfigPayload())
      const response = await api.post('/api/video/start')
      const data = await response.json()
      if (response.ok && data.success) {
        showToast(t('views.video.streamStarted'), 'success')
      } else {
        showToast(data.detail || data.message || t('views.video.errorStarting'), 'error')
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
      if (response.ok && data.success) {
        showToast(t('views.video.streamStopped'), 'success')
      } else {
        showToast(data.detail || data.message || t('views.video.errorStopping'), 'error')
      }
    } catch (error) {
      showToast(error.message || t('views.video.errorStopping'), 'error')
    }
    setActionLoading(null)
  }

  const restartStream = async () => {
    setActionLoading('restart')
    try {
      await api.post('/api/video/config/video', buildVideoConfigPayload())
      const response = await api.post('/api/video/restart')
      const data = await response.json()
      if (response.ok && data.success) {
        showToast(t('views.video.streamRestarted'), 'success')

        // Force WebRTC component remount by changing key
        // This ensures clean reconnection with fresh state
        if (config.mode === 'webrtc') {
          setWebrtcKey((prev) => prev + 1)
        }
      } else {
        showToast(data.detail || data.message || t('views.video.errorRestarting'), 'error')
      }
    } catch (error) {
      showToast(error.message || t('views.video.errorRestarting'), 'error')
    }
    setActionLoading(null)
  }

  const applySettings = async () => {
    setActionLoading('apply')
    try {
      const videoRes = await api.post('/api/video/config/video', buildVideoConfigPayload())
      const streamRes = await api.post('/api/video/config/streaming', {
        mode: config.mode,
        udp_host: config.udp_host,
        udp_port: safeInt(config.udp_port, VIDEO_DEFAULTS.UDP_PORT),
        multicast_group: config.multicast_group,
        multicast_port: safeInt(config.multicast_port, VIDEO_DEFAULTS.MULTICAST_PORT),
        multicast_ttl: safeInt(config.multicast_ttl, VIDEO_DEFAULTS.MULTICAST_TTL),
        rtsp_enabled: config.rtsp_enabled,
        rtsp_url: config.rtsp_url,
        rtsp_transport: config.rtsp_transport,
        auto_start: config.auto_start,
      })

      const videoData = await videoRes.json()
      const streamData = await streamRes.json()

      if (videoRes.ok && streamRes.ok && videoData.success && streamData.success) {
        setHasChanges(false)
        if (status.streaming) {
          const restartRes = await api.post('/api/video/restart')
          const restartData = await restartRes.json()
          if (restartRes.ok && restartData.success) {
            showToast(t('views.video.configAppliedAndRestarted'), 'success')
            // Force WebRTC component remount after restart
            if (config.mode === 'webrtc') {
              setWebrtcKey((prev) => prev + 1)
            }
          } else {
            const msg =
              typeof restartData.detail === 'string' ? restartData.detail : restartData.message
            showToast(msg || t('views.video.configSavedRestartError'), 'warning')
          }
        } else {
          showToast(t('views.video.configAppliedAndSaved'), 'success')
        }
      } else {
        const errMsg =
          (typeof videoData.detail === 'string' && videoData.detail) ||
          (typeof streamData.detail === 'string' && streamData.detail) ||
          (Array.isArray(streamData.detail) && streamData.detail.map((e) => e.msg).join('; ')) ||
          (Array.isArray(videoData.detail) && videoData.detail.map((e) => e.msg).join('; ')) ||
          videoData.message ||
          streamData.message ||
          t('views.video.errorApplying')
        showToast(errMsg, 'error')
      }
    } catch (error) {
      showToast(error.message || t('views.video.errorApplying'), 'error')
    }
    setActionLoading(null)
  }

  // Live update — change property on-the-fly without restart
  const liveUpdate = useCallback(
    async (property, value) => {
      try {
        const response = await api.post('/api/video/live-update', {
          property,
          value: safeInt(value, 0),
        })
        const data = await response.json()
        if (!response.ok || !data.success) {
          showToast(data.detail || data.message || t('views.video.errorLiveUpdate'), 'error')
        }
      } catch (error) {
        showToast(error.message || t('views.video.errorLiveUpdate'), 'error')
      }
    },
    [showToast, t]
  )

  const debouncedLiveUpdate = useCallback(
    (property, value) => {
      clearTimeout(liveUpdateTimer.current)
      liveUpdateTimer.current = setTimeout(
        () => liveUpdate(property, value),
        TIMING.DEBOUNCE_LIVE_UPDATE
      )
    },
    [liveUpdate]
  )

  // Clipboard copy — modern API with execCommand fallback for non-secure contexts (HTTP over LAN)
  const copyPipeline = useCallback(
    async (text) => {
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text)
        } else {
          const textarea = document.createElement('textarea')
          textarea.value = text
          textarea.style.position = 'fixed'
          textarea.style.opacity = '0'
          document.body.appendChild(textarea)
          textarea.select()
          document.execCommand('copy')
          document.body.removeChild(textarea)
        }
        setCopySuccess(true)
        showToast(t('views.video.pipelineCopied'), 'success')
        setTimeout(() => setCopySuccess(false), TIMING.COPY_SUCCESS_DURATION)
      } catch (_error) {
        showToast(t('views.video.errorCopying'), 'error')
      }
    },
    [showToast, t]
  )

  // ── Memoized derived values ────────────────────────────────────────────────
  const currentCamera = useMemo(
    () => cameras.find((cam) => cam.device === config.device) || cameras[0],
    [cameras, config.device]
  )

  const availableResolutions = useMemo(() => currentCamera?.resolutions || [], [currentCamera])

  const currentResolution = `${config.width}x${config.height}`

  const availableFps = useMemo(
    () => currentCamera?.resolutions_fps?.[currentResolution] || FALLBACK_FPS,
    [currentCamera, currentResolution]
  )

  // Auto-select first camera if configured device doesn't exist
  useEffect(() => {
    if (cameras.length > 0 && !cameras.find((cam) => cam.device === config.device)) {
      const firstCam = cameras[0]
      if (firstCam.resolutions?.length > 0) {
        const firstRes = firstCam.resolutions[0]
        const [w, h] = firstRes.split('x')
        const fps = firstCam.resolutions_fps?.[firstRes]?.[0] || VIDEO_DEFAULTS.FRAMERATE
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setConfig((prev) => ({
          ...prev,
          device: firstCam.device,
          width: safeInt(w, VIDEO_DEFAULTS.WIDTH),
          height: safeInt(h, VIDEO_DEFAULTS.HEIGHT),
          framerate: fps,
        }))
      }
    }
  }, [cameras, config.device])

  // Handle camera change — reset to first available resolution
  const handleCameraChange = useCallback(
    (device) => {
      const camera = cameras.find((cam) => cam.device === device)
      if (camera?.resolutions?.length > 0) {
        const firstRes = camera.resolutions[0]
        const [w, h] = firstRes.split('x')
        const fps = camera.resolutions_fps?.[firstRes]?.[0] || VIDEO_DEFAULTS.FRAMERATE
        updateConfig((prev) => ({
          ...prev,
          device,
          width: safeInt(w, VIDEO_DEFAULTS.WIDTH),
          height: safeInt(h, VIDEO_DEFAULTS.HEIGHT),
          framerate: fps,
        }))
      } else {
        updateConfig((prev) => ({ ...prev, device }))
      }
    },
    [cameras, updateConfig]
  )

  // Handle resolution change — reset to first available FPS
  const handleResolutionChange = useCallback(
    (resolution) => {
      const [w, h] = resolution.split('x')
      const fps = currentCamera?.resolutions_fps?.[resolution]?.[0] || VIDEO_DEFAULTS.FRAMERATE
      updateConfig((prev) => ({
        ...prev,
        width: safeInt(w, VIDEO_DEFAULTS.WIDTH),
        height: safeInt(h, VIDEO_DEFAULTS.HEIGHT),
        framerate: fps,
      }))
    },
    [currentCamera, updateConfig]
  )

  // Pipeline string from backend (no more client-side duplication)
  const pipelineString = status.pipeline_string || ''

  // ── Render ─────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="card">
        <h2>{t('views.video.title')}</h2>
        <div className="waiting-data">
          <div className="spinner-small"></div>
          {t('common.loadingContent')}
        </div>
      </div>
    )
  }

  if (!status.available) {
    return (
      <div className="card">
        <h2>{t('views.video.title')}</h2>
        <div className="error-box">{t('views.video.gstreamerNotAvailable')}</div>
      </div>
    )
  }

  return (
    <div className="video-view">
      <StatusBanner status={status} config={config} />

      <div className="video-columns">
        {/* Left Column — Video Settings */}
        <div className="video-col">
          <VideoSourceCard
            config={config}
            cameras={cameras}
            streaming={status.streaming}
            handleCameraChange={handleCameraChange}
            handleResolutionChange={handleResolutionChange}
            updateConfig={updateConfig}
            availableResolutions={availableResolutions}
            availableFps={availableFps}
          />
          {config.mode !== 'webrtc' && (
            <EncodingConfigCard
              config={config}
              streaming={status.streaming}
              availableCodecs={availableCodecs}
              updateConfig={updateConfig}
              debouncedLiveUpdate={debouncedLiveUpdate}
              liveUpdate={liveUpdate}
              autoAdaptiveBitrate={autoAdaptiveBitrate}
            />
          )}
          <NetworkSettingsCard
            config={config}
            streaming={status.streaming}
            updateConfig={updateConfig}
            webrtcStatus={webrtcStatus}
            onValidationChange={handleNetworkValidation}
          />
        </div>

        {/* Right Column — Controls & Pipeline */}
        <div className="video-col">
          <StreamControlCard
            streaming={status.streaming}
            actionLoading={actionLoading}
            applySettings={applySettings}
            applyConfigAndStart={applyConfigAndStart}
            stopStream={stopStream}
            restartStream={restartStream}
            config={config}
            updateConfig={updateConfig}
            hasValidationErrors={networkValidationErrors}
          />
          {/* WebRTC Viewer — shown when WebRTC mode is active and streaming */}
          {config.mode === 'webrtc' && status.streaming && (
            <WebRTCViewerCard
              key={webrtcKey}
              ref={webrtcViewerRef}
              status={status}
              webrtcStatus={webrtcStatus}
              onStatsUpdate={setWebrtcVideoStats}
            />
          )}
          {/* Pipeline Card — hidden for WebRTC */}
          {status.streaming && config.mode !== 'webrtc' && (
            <PipelineCard
              pipelineString={pipelineString}
              onCopy={copyPipeline}
              copySuccess={copySuccess}
            />
          )}
          {status.streaming && status.stats && (
            <StatsCard
              status={status}
              webrtcVideoStats={webrtcVideoStats}
              autoAdaptiveBitrate={autoAdaptiveBitrate}
            />
          )}
        </div>
      </div>
    </div>
  )
}

export default VideoView
