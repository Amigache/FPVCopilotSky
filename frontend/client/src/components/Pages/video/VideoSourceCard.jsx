import { useTranslation } from 'react-i18next'
import { safeInt, VIDEO_DEFAULTS } from './videoConstants'

const VideoSourceCard = ({
  config,
  cameras,
  streaming,
  handleCameraChange,
  handleResolutionChange,
  updateConfig,
  availableResolutions,
  availableFps,
}) => {
  const { t } = useTranslation()

  return (
    <div className="card">
      <h2>{t('views.video.videoSourceSelection')}</h2>

      <div className={`form-group ${streaming ? 'field-disabled' : ''}`}>
        <label>{t('views.video.videoSource')}</label>
        <select
          value={config.device}
          onChange={(e) => handleCameraChange(e.target.value)}
          disabled={streaming}
        >
          {cameras.length === 0 ? (
            <option value="">{t('views.video.noCamerasAvailable')}</option>
          ) : (
            cameras.map((cam) => (
              <option key={cam.device} value={cam.device}>
                {cam.name} {cam.provider && `[${cam.provider}]`} ({cam.device})
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
