import { useTranslation } from 'react-i18next'
import { safeInt, VIDEO_DEFAULTS } from './videoConstants'

const SOURCE_TYPE_ICONS = {
  v4l2: '📷',
  libcamera: '🎥',
  hdmi_capture: '🖥️',
  network_stream: '🌐',
}

const VideoSourceCard = ({
  config,
  videoDevices,
  streaming,
  handleCameraChange,
  handleResolutionChange,
  updateConfig,
  availableResolutions,
  availableFps,
}) => {
  const { t } = useTranslation()

  return (
    <div className="card" data-testid="video-source-card">
      <h2>{t('views.video.videoSourceSelection')}</h2>

      <div className={`form-group ${streaming ? 'field-disabled' : ''}`}>
        <label>{t('views.video.videoSource')}</label>
        <select
          value={config.device}
          onChange={(e) => handleCameraChange(e.target.value)}
          disabled={streaming}
        >
          {videoDevices.length === 0 ? (
            <option value="">{t('views.video.noCamerasAvailable')}</option>
          ) : (
            videoDevices.map((dev) => (
              <option key={dev.device_id} value={dev.device_path}>
                {SOURCE_TYPE_ICONS[dev.source_type] || '📷'} {dev.name} [{dev.provider}] (
                {dev.device_path})
              </option>
            ))
          )}
        </select>
      </div>

      <div className="form-row">
        <div className={`form-group ${streaming ? 'field-disabled' : ''}`}>
          <label>{t('views.video.resolution')}</label>
          <select
            value={`${config.width}x${config.height}`}
            onChange={(e) => handleResolutionChange(e.target.value)}
            disabled={streaming}
          >
            {availableResolutions.length > 0 ? (
              availableResolutions.map((res) => (
                <option key={res} value={res}>
                  {res}
                </option>
              ))
            ) : (
              <option value={`${config.width}x${config.height}`}>
                {config.width}x{config.height}
              </option>
            )}
          </select>
        </div>

        <div className={`form-group ${streaming ? 'field-disabled' : ''}`}>
          <label>{t('views.video.fps')}</label>
          <select
            value={config.framerate}
            onChange={(e) =>
              updateConfig((prev) => ({
                ...prev,
                framerate: safeInt(e.target.value, VIDEO_DEFAULTS.FRAMERATE),
              }))
            }
            disabled={streaming}
          >
            {availableFps.map((fps) => (
              <option key={fps} value={fps}>
                {fps} fps
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  )
}

export default VideoSourceCard
