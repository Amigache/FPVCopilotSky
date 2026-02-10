import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  RANGES,
  VIDEO_DEFAULTS,
  safeInt,
  isValidMulticastIp,
  validatePort,
  validateRtspUrl,
  isValidHost,
} from './videoConstants'

const NetworkSettingsCard = ({
  config,
  streaming,
  updateConfig,
  webrtcStatus,
  onValidationChange,
}) => {
  const { t } = useTranslation()

  // Inline validation helpers
  const multicastError =
    config.mode === 'multicast' &&
    config.multicast_group &&
    !isValidMulticastIp(config.multicast_group)

  const rtspValidation =
    config.mode === 'rtsp' && config.rtsp_url ? validateRtspUrl(config.rtsp_url) : { valid: true }

  // UDP host validation
  const udpHostValidation =
    config.mode === 'udp'
      ? config.udp_host && config.udp_host.trim() !== ''
        ? { valid: isValidHost(config.udp_host), error: 'views.video.validation.invalidHost' }
        : { valid: false, error: 'views.video.validation.emptyHost' }
      : { valid: true }

  // Port validations - check if empty or invalid
  const udpPortValidation =
    config.mode === 'udp'
      ? config.udp_port === '' || config.udp_port === null || config.udp_port === undefined
        ? { valid: false, error: 'views.video.validation.emptyPort' }
        : validatePort(config.udp_port)
      : { valid: true }

  const multicastPortValidation =
    config.mode === 'multicast'
      ? config.multicast_port === '' ||
        config.multicast_port === null ||
        config.multicast_port === undefined
        ? { valid: false, error: 'views.video.validation.emptyPort' }
        : validatePort(config.multicast_port)
      : { valid: true }

  // Calculate if there are any validation errors
  const hasErrors =
    !udpHostValidation.valid ||
    !udpPortValidation.valid ||
    !multicastPortValidation.valid ||
    multicastError ||
    !rtspValidation.valid

  // Notify parent of validation state changes
  useEffect(() => {
    if (onValidationChange) {
      onValidationChange(hasErrors)
    }
  }, [hasErrors, onValidationChange])

  return (
    <div className={`card ${streaming ? 'card-disabled' : ''}`} data-testid="network-card">
      <h2>{t('views.video.networkUdpRtp')}</h2>

      {/* Streaming Mode Selector */}
      <div className={`form-group ${streaming ? 'field-disabled' : ''}`}>
        <label>{t('views.video.streamingMode')}</label>
        <select
          value={config.mode || VIDEO_DEFAULTS.MODE}
          onChange={(e) => updateConfig((prev) => ({ ...prev, mode: e.target.value }))}
          disabled={streaming}
        >
          <option value="udp">{t('views.video.modeUdp')}</option>
          <option value="multicast">{t('views.video.modeMulticast')}</option>
          <option value="rtsp">{t('views.video.modeRtsp')}</option>
          <option value="webrtc">{t('views.video.modeWebrtc')}</option>
        </select>
        <small>
          {config.mode === 'udp' && t('views.video.modeUdpDesc')}
          {config.mode === 'multicast' && t('views.video.modeMulticastDesc')}
          {config.mode === 'rtsp' && t('views.video.modeRtspDesc')}
          {config.mode === 'webrtc' && t('views.video.modeWebrtcDesc')}
        </small>
      </div>

      {/* UDP Unicast Settings */}
      {config.mode === 'udp' && (
        <div className="form-row">
          <div className={`form-group ${streaming ? 'field-disabled' : ''}`}>
            <label>{t('views.video.destination')}</label>
            <input
              type="text"
              value={config.udp_host || ''}
              onChange={(e) => updateConfig((prev) => ({ ...prev, udp_host: e.target.value }))}
              placeholder="192.168.1.100"
              disabled={streaming}
              className={!udpHostValidation.valid ? 'input-error' : ''}
            />
            {!udpHostValidation.valid && (
              <small className="field-error">{t(udpHostValidation.error)}</small>
            )}
            <small>{t('views.video.destinationHint')}</small>
          </div>
          <div className={`form-group ${streaming ? 'field-disabled' : ''}`}>
            <label>{t('views.video.udpPort')}</label>
            <input
              type="number"
              value={config.udp_port ?? ''}
              min={RANGES.PORT.MIN}
              max={RANGES.PORT.MAX}
              onChange={(e) => {
                const value = e.target.value
                updateConfig((prev) => ({
                  ...prev,
                  udp_port: value === '' ? '' : parseInt(value, 10),
                }))
              }}
              disabled={streaming}
              className={!udpPortValidation.valid ? 'input-error' : ''}
            />
            {!udpPortValidation.valid && (
              <small className="field-error">{t(udpPortValidation.error)}</small>
            )}
          </div>
        </div>
      )}

      {/* UDP Multicast Settings */}
      {config.mode === 'multicast' && (
        <>
          <div className="form-row">
            <div className={`form-group ${streaming ? 'field-disabled' : ''}`}>
              <label>{t('views.video.multicastGroup')}</label>
              <input
                type="text"
                value={config.multicast_group || VIDEO_DEFAULTS.MULTICAST_GROUP}
                onChange={(e) =>
                  updateConfig((prev) => ({ ...prev, multicast_group: e.target.value }))
                }
                placeholder={VIDEO_DEFAULTS.MULTICAST_GROUP}
                disabled={streaming}
                className={multicastError ? 'input-error' : ''}
              />
              {multicastError ? (
                <small className="field-error">{t('views.video.multicastValidRange')}</small>
              ) : (
                <small>{t('views.video.multicastValidRange')}</small>
              )}
            </div>
            <div className={`form-group ${streaming ? 'field-disabled' : ''}`}>
              <label>{t('views.video.multicastPort')}</label>
              <input
                type="number"
                value={config.multicast_port ?? ''}
                min={RANGES.PORT.MIN}
                max={RANGES.PORT.MAX}
                onChange={(e) => {
                  const value = e.target.value
                  updateConfig((prev) => ({
                    ...prev,
                    multicast_port: value === '' ? '' : parseInt(value, 10),
                  }))
                }}
                disabled={streaming}
                className={!multicastPortValidation.valid ? 'input-error' : ''}
              />
              {!multicastPortValidation.valid && (
                <small className="field-error">{t(multicastPortValidation.error)}</small>
              )}
            </div>
          </div>
          <div className={`form-group ${streaming ? 'field-disabled' : ''}`}>
            <label>{t('views.video.ttl')}</label>
            <input
              type="number"
              value={config.multicast_ttl || VIDEO_DEFAULTS.MULTICAST_TTL}
              min={RANGES.TTL.MIN}
              max={RANGES.TTL.MAX}
              onChange={(e) =>
                updateConfig((prev) => ({
                  ...prev,
                  multicast_ttl: safeInt(e.target.value, VIDEO_DEFAULTS.MULTICAST_TTL),
                }))
              }
              disabled={streaming}
            />
            <small>{t('views.video.ttlHint')}</small>
          </div>
        </>
      )}

      {/* RTSP Server Settings */}
      {config.mode === 'rtsp' && (
        <>
          <div className={`form-group ${streaming ? 'field-disabled' : ''}`}>
            <label>{t('views.video.rtspUrl')}</label>
            <input
              type="text"
              value={config.rtsp_url || VIDEO_DEFAULTS.RTSP_URL}
              onChange={(e) => updateConfig((prev) => ({ ...prev, rtsp_url: e.target.value }))}
              placeholder={VIDEO_DEFAULTS.RTSP_URL}
              disabled={streaming}
              className={!rtspValidation.valid ? 'input-error' : ''}
            />
            {!rtspValidation.valid ? (
              <small className="field-error">{t(rtspValidation.error)}</small>
            ) : (
              <small>{t('views.video.rtspUrlHint')}</small>
            )}
          </div>
          <div className={`form-group ${streaming ? 'field-disabled' : ''}`}>
            <label>{t('views.video.rtspTransport')}</label>
            <select
              value={config.rtsp_transport || VIDEO_DEFAULTS.RTSP_TRANSPORT}
              onChange={(e) =>
                updateConfig((prev) => ({ ...prev, rtsp_transport: e.target.value }))
              }
              disabled={streaming}
            >
              <option value="tcp">{t('views.video.rtspTcp')}</option>
              <option value="udp">{t('views.video.rtspUdp')}</option>
            </select>
          </div>
        </>
      )}

      {/* WebRTC Settings */}
      {config.mode === 'webrtc' && (
        <div className="info-box">{t('views.video.modeWebrtcInfo')}</div>
      )}

      {/* WebRTC Log — at the bottom of this card when webrtc mode */}
      {config.mode === 'webrtc' && (
        <WebRTCLogInline webrtcStatus={webrtcStatus} streaming={streaming} />
      )}
    </div>
  )
}

/** Inline collapsible WebRTC log */
const WebRTCLogInline = ({ webrtcStatus, streaming }) => {
  const { t } = useTranslation()
  const [logExpanded, setLogExpanded] = useState(false)
  const logEndRef = useRef(null)

  const logs = webrtcStatus?.log || []

  useEffect(() => {
    if (logExpanded && logEndRef.current && logEndRef.current.scrollIntoView) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs.length, logExpanded])

  const formatTimestamp = (ts) => {
    const d = new Date(ts * 1000)
    return d.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  const levelColors = {
    info: 'var(--color-accent)',
    success: 'var(--color-success)',
    warning: 'var(--color-warning)',
    error: 'var(--color-error)',
  }
  const levelIcons = { info: 'ℹ️', success: '✅', warning: '⚠️', error: '❌' }

  if (!streaming) return null

  return (
    <div className="webrtc-log-inline">
      <div
        className="webrtc-log-header"
        onClick={() => setLogExpanded(!logExpanded)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') setLogExpanded(!logExpanded)
        }}
      >
        <span className="webrtc-log-title">
          {t('views.video.webrtcLog')}
          <span className="webrtc-log-count">{logs.length}</span>
        </span>
        <span className="webrtc-log-toggle">{logExpanded ? '▲' : '▼'}</span>
      </div>

      {logExpanded && (
        <div className="webrtc-log-body">
          {logs.length === 0 ? (
            <div className="webrtc-log-empty">{t('views.video.webrtcLogEmpty')}</div>
          ) : (
            <div className="webrtc-log-list">
              {logs.map((entry, idx) => (
                <div key={idx} className="webrtc-log-entry">
                  <span className="webrtc-log-time">{formatTimestamp(entry.timestamp)}</span>
                  <span className="webrtc-log-icon">{levelIcons[entry.level] || 'ℹ️'}</span>
                  <span
                    className="webrtc-log-message"
                    style={{ color: levelColors[entry.level] || 'inherit' }}
                  >
                    {entry.message}
                  </span>
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default NetworkSettingsCard
