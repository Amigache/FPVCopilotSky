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
  const [videoDevices, setVideoDevices] = useState([])
  const [systemCodecs, setSystemCodecs] = useState([])
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
    const device = videoDevices.find((d) => d.device_path === config.device)
    return {
      device: config.device,
      device_name: device?.name || '',
      device_bus_info: device?.bus_info || '',
      width: safeInt(config.width, VIDEO_DEFAULTS.WIDTH),
      height: safeInt(config.height, VIDEO_DEFAULTS.HEIGHT),
      framerate: safeInt(config.framerate, VIDEO_DEFAULTS.FRAMERATE),
      codec: config.codec,
      quality: safeInt(config.quality, VIDEO_DEFAULTS.QUALITY),
      h264_bitrate: safeInt(config.h264_bitrate, VIDEO_DEFAULTS.H264_BITRATE),
      gop_size: safeInt(config.gop_size, VIDEO_DEFAULTS.GOP_SIZE),
    }
  }, [videoDevices, config])

  // ── WebSocket status ───────────────────────────────────────────────────────
  const status = messages.video_status || EMPTY_STATUS
  const webrtcStatus = messages.webrtc_status || null

  // Sync remote config → local when no pending changes
  useEffect(() => {
    if (messages.video_status?.config && !hasChanges) {
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
  const loadVideoDevices = useCallback(async () => {
    try {
      const response = await api.get('/api/system/video-devices')
      if (response.ok) {
        const data = await response.json()
        setVideoDevices(data.devices || [])
      }
    } catch (error) {
      console.error('Error loading video devices:', error)
    }
  }, [])

  const loadCodecs = useCallback(async () => {
    try {
      const response = await api.get('/api/video/codecs')
      if (response.ok) {
        const data = await response.json()
        setSystemCodecs(data.codecs || [])
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
      await Promise.all([
        loadVideoDevices(),
        loadCodecs(),
        loadNetworkIp(),
        loadAutoAdaptiveBitrate(),
      ])
      setLoading(false)
    }
    loadData()
  }, [loadVideoDevices, loadCodecs, loadNetworkIp, loadAutoAdaptiveBitrate])

  // RTSP mode: auto-populate URL + reload network IP (merged from two effects)
  useEffect(() => {
    if (config.mode === 'rtsp' && initialLoadDone.current) {
      if (networkIp) {
        const isDefaultUrl = config.rtsp_url === VIDEO_DEFAULTS.RTSP_URL || !config.rtsp_url
        if (isDefaultUrl && networkIp.rtsp_url) {
          updateConfig((prev) => ({ ...prev, rtsp_url: networkIp.rtsp_url }))
        }
      }
      loadNetworkIp()
    }
  }, [config.mode]) // eslint-disable-line react-hooks/exhaustive-deps

  // Listen for resolution changes from auto-adaptive system
  useEffect(() => {
    if (messages.resolution_changed) {
      const { old_resolution, new_resolution, reason } = messages.resolution_changed
      const reasonText =
        reason === 'adaptive_downscale'
          ? t('views.video.qualityDrop')
          : t('views.video.qualityRestore')
      showToast(
        `📐 ${t(
          'views.video.resolutionAdjusted'
        )}: ${old_resolution} → ${new_resolution} (${reasonText})`,
        'info'
      )
    }
  }, [messages.resolution_changed, showToast, t])

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
  const currentDevice = useMemo(
    () => videoDevices.find((d) => d.device_path === config.device) || videoDevices[0],
    [videoDevices, config.device]
  )

  const availableResolutions = useMemo(() => currentDevice?.resolutions || [], [currentDevice])

  const currentResolution = `${config.width}x${config.height}`

  const availableFps = useMemo(
    () => currentDevice?.fps_by_resolution?.[currentResolution] || FALLBACK_FPS,
    [currentDevice, currentResolution]
  )

  // Derive available codecs from the selected device's compatible_codecs + system codecs
  useEffect(() => {
    if (!currentDevice || systemCodecs.length === 0) return

    const deviceCodecs = currentDevice.compatible_codecs || []
    const compatibleIds = new Set(deviceCodecs.filter((c) => c.compatible).map((c) => c.codec_id))

    // Filter system codecs to only those compatible with this device
    const filtered = systemCodecs.filter((c) => compatibleIds.has(c.id))

    setAvailableCodecs(filtered)

    // Determine best codec for this device:
    // - Prefer passthrough for H264-capable cameras (ultra-low latency)
    // - Otherwise keep current codec if compatible, else switch to first compatible
    if (filtered.length > 0) {
      const hasPassthrough = deviceCodecs.some(
        (c) => c.codec_id === 'h264_passthrough' && c.compatible
      )
      const passthroughCodec = filtered.find((c) => c.id === 'h264_passthrough')
      const currentCompatible = filtered.some((c) => c.id === config.codec)

      if (hasPassthrough && passthroughCodec && config.codec !== 'h264_passthrough') {
        setConfig((prev) => ({ ...prev, codec: 'h264_passthrough' }))
      } else if (!currentCompatible) {
        setConfig((prev) => ({ ...prev, codec: filtered[0].id }))
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentDevice, systemCodecs])

  // Auto-select first device if configured device doesn't exist
  useEffect(() => {
    if (videoDevices.length > 0 && !videoDevices.find((d) => d.device_path === config.device)) {
      const firstDev = videoDevices[0]
      if (firstDev.resolutions?.length > 0) {
        const firstRes = firstDev.resolutions[0]
        const [w, h] = firstRes.split('x')
        const fps = firstDev.fps_by_resolution?.[firstRes]?.[0] || VIDEO_DEFAULTS.FRAMERATE
        setConfig((prev) => ({
          ...prev,
          device: firstDev.device_path,
          width: safeInt(w, VIDEO_DEFAULTS.WIDTH),
          height: safeInt(h, VIDEO_DEFAULTS.HEIGHT),
          framerate: fps,
        }))
      }
    }
  }, [videoDevices, config.device])

  // Handle camera change — reset to first available resolution
  const handleCameraChange = useCallback(
    (devicePath) => {
      const device = videoDevices.find((d) => d.device_path === devicePath)
      if (device?.resolutions?.length > 0) {
        const firstRes = device.resolutions[0]
        const [w, h] = firstRes.split('x')
        const fps = device.fps_by_resolution?.[firstRes]?.[0] || VIDEO_DEFAULTS.FRAMERATE
        updateConfig((prev) => ({
          ...prev,
          device: devicePath,
          width: safeInt(w, VIDEO_DEFAULTS.WIDTH),
          height: safeInt(h, VIDEO_DEFAULTS.HEIGHT),
          framerate: fps,
        }))
      } else {
        updateConfig((prev) => ({ ...prev, device: devicePath }))
      }
    },
    [videoDevices, updateConfig]
  )

  // Handle resolution change — reset to first available FPS
  const handleResolutionChange = useCallback(
    (resolution) => {
      const [w, h] = resolution.split('x')
      const fps = currentDevice?.fps_by_resolution?.[resolution]?.[0] || VIDEO_DEFAULTS.FRAMERATE
      updateConfig((prev) => ({
        ...prev,
        width: safeInt(w, VIDEO_DEFAULTS.WIDTH),
        height: safeInt(h, VIDEO_DEFAULTS.HEIGHT),
        framerate: fps,
      }))
    },
    [currentDevice, updateConfig]
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
            videoDevices={videoDevices}
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
