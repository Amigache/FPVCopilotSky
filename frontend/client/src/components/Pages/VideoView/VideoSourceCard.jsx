import { useTranslation } from 'react-i18next'
import { safeInt, VIDEO_DEFAULTS } from './videoConstants'

const VideoSourceCard = ({
  config,
  cameras,
  videoSources = [], // New: video sources from providers
  streaming,
  handleCameraChange,
  handleResolutionChange,
  updateConfig,
  availableResolutions,
  availableFps,
}) => {
  const { t } = useTranslation()

  // Combine legacy cameras and new video sources for backward compatibility
  const allSources = [
    ...cameras.map((cam) => ({
      id: cam.device,
      name: cam.name,
      device_path: cam.device,
      type: 'legacy',
      provider: cam.provider,
    })),
    ...videoSources
      .filter((source) => source.available)
      .map((source) => ({
        id: source.id,
        name: source.name,
        device_path: source.device_path,
        type: source.type,
        provider: source.type,
      })),
  ]

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
          {allSources.length === 0 ? (
            <option value="">{t('views.video.noCamerasAvailable')}</option>
          ) : (
            allSources.map((source) => (
              <option key={source.id} value={source.device_path}>
                {source.name} [{source.provider}] ({source.device_path})
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
