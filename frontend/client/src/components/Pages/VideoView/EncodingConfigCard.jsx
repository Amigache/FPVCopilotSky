import { useTranslation } from 'react-i18next'
import { BITRATE_OPTIONS, GOP_OPTIONS, RANGES, VIDEO_DEFAULTS, safeInt } from './videoConstants'

const EncodingConfigCard = ({
  config,
  streaming,
  availableCodecs,
  updateConfig,
  debouncedLiveUpdate,
  liveUpdate,
}) => {
  const { t } = useTranslation()
  const isLiveEditable = streaming && config.mode === 'udp'
  const isH264 =
    config.codec === 'h264' || config.codec === 'h264_openh264' || config.codec === 'h264_hardware'

  return (
    <div className="card" data-testid="encoding-card">
      <h2>{t('views.video.encodingConfiguration')}</h2>

      {/* Codec selector */}
      <div className={`form-group ${streaming ? 'field-disabled' : ''}`}>
        <label>
          {t('views.video.codec')}
          {availableCodecs.length > 0 && (
            <span className="field-hint">
              {availableCodecs.length} {t('views.video.codecsAvailable')}
            </span>
          )}
        </label>
        <select
          value={config.codec}
          onChange={(e) => {
            updateConfig((prev) => ({ ...prev, codec: e.target.value }))
            const selectedCodec = availableCodecs.find((c) => c.id === e.target.value)
            if (selectedCodec?.default_bitrate) {
              updateConfig((prev) => ({ ...prev, h264_bitrate: selectedCodec.default_bitrate }))
            }
          }}
          disabled={streaming || availableCodecs.length === 0}
        >
          {availableCodecs.length === 0 ? (
            <>
              <option value="mjpeg">{t('views.video.codecMjpeg')}</option>
              <option value="h264">{t('views.video.codecH264')}</option>
            </>
          ) : (
            availableCodecs.map((codec) => (
              <option key={codec.id} value={codec.id}>
                {codec.name}
                {codec.description &&
                  ` - ${t('views.video.codecCpuLatency', {
                    cpu: codec.cpu_usage,
                    latency: codec.latency,
                  })}`}
              </option>
            ))
          )}
        </select>
        {availableCodecs.length > 0 && config.codec && (
          <small className="codec-info">
            {availableCodecs.find((c) => c.id === config.codec)?.description || ''}
          </small>
        )}
      </div>

      {/* MJPEG Quality Slider */}
      {config.codec === 'mjpeg' && (
        <div
          className={`form-group ${
            isLiveEditable ? 'field-live' : streaming ? 'field-disabled' : ''
          }`}
        >
          <label>
            {t('views.video.jpegQuality')}: {config.quality}
            {isLiveEditable && <span className="live-tag">LIVE</span>}
          </label>
          <input
            type="range"
            min={RANGES.QUALITY.MIN}
            max={RANGES.QUALITY.MAX}
            value={config.quality}
            onChange={(e) => {
              const val = safeInt(e.target.value, VIDEO_DEFAULTS.QUALITY)
              updateConfig((prev) => ({ ...prev, quality: val }))
              if (isLiveEditable) debouncedLiveUpdate('quality', val)
            }}
            disabled={streaming && !isLiveEditable}
            className="slider"
          />
        </div>
      )}

      {/* H.264 Bitrate & GOP */}
      {isH264 && (
        <>
          <div
            className={`form-group ${
              isLiveEditable ? 'field-live' : streaming ? 'field-disabled' : ''
            }`}
          >
            <label>
              {t('views.video.bitrate')}
              {isLiveEditable && <span className="live-tag">LIVE</span>}
            </label>
            <select
              value={config.h264_bitrate}
              onChange={(e) => {
                const val = safeInt(e.target.value, VIDEO_DEFAULTS.H264_BITRATE)
                updateConfig((prev) => ({ ...prev, h264_bitrate: val }))
                if (isLiveEditable) liveUpdate('bitrate', val)
              }}
              disabled={streaming && !isLiveEditable}
            >
              {BITRATE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.value}
                  {opt.labelKey ? ` (${t(`views.video.${opt.labelKey}`)})` : ''}
                </option>
              ))}
            </select>
          </div>

          {/* GOP size — only for OpenH264 */}
          {config.codec === 'h264_openh264' && (
            <div
              className={`form-group ${
                isLiveEditable ? 'field-live' : streaming ? 'field-disabled' : ''
              }`}
            >
              <label>
                {t('views.video.keyframeInterval')}
                {isLiveEditable && <span className="live-tag">LIVE</span>}
              </label>
              <select
                value={config.gop_size || VIDEO_DEFAULTS.GOP_SIZE}
                onChange={(e) => {
                  const val = safeInt(e.target.value, VIDEO_DEFAULTS.GOP_SIZE)
                  updateConfig((prev) => ({ ...prev, gop_size: val }))
                  if (isLiveEditable) liveUpdate('gop-size', val)
                }}
                disabled={streaming && !isLiveEditable}
              >
                {GOP_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.value} ({t(`views.video.${opt.labelKey}`)})
                  </option>
                ))}
              </select>
              <small>
                {t('views.video.keyframesPerSecond', {
                  fps: config.framerate || VIDEO_DEFAULTS.FRAMERATE,
                  value: Math.round(
                    (config.framerate || VIDEO_DEFAULTS.FRAMERATE) /
                      (config.gop_size || VIDEO_DEFAULTS.GOP_SIZE)
                  ),
                })}
              </small>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default EncodingConfigCard
