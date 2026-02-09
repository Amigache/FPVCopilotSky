import { useTranslation } from 'react-i18next'
import { PeerSelector } from '../../PeerSelector/PeerSelector'
import Toggle from '../../Toggle/Toggle'
import { RANGES, VIDEO_DEFAULTS, safeInt, isValidMulticastIp } from './videoConstants'

const NetworkSettingsCard = ({ config, streaming, updateConfig }) => {
  const { t } = useTranslation()

  // Inline validation helpers
  const multicastError =
    config.mode === 'multicast' &&
    config.multicast_group &&
    !isValidMulticastIp(config.multicast_group)
  const rtspUrlError =
    config.mode === 'rtsp' && config.rtsp_url && !config.rtsp_url.startsWith('rtsp://')

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
        </select>
        <small>
          {config.mode === 'udp' && t('views.video.modeUdpDesc')}
          {config.mode === 'multicast' && t('views.video.modeMulticastDesc')}
          {config.mode === 'rtsp' && t('views.video.modeRtspDesc')}
        </small>
      </div>

      {/* UDP Unicast Settings */}
      {config.mode === 'udp' && (
        <div className="form-row">
          <div className={`form-group ${streaming ? 'field-disabled' : ''}`}>
            <PeerSelector
              label={t('views.video.destinationIp')}
              value={config.udp_host}
              onChange={(value) => updateConfig((prev) => ({ ...prev, udp_host: value }))}
              placeholder="192.168.1.100"
              disabled={streaming}
            />
          </div>
          <div className={`form-group ${streaming ? 'field-disabled' : ''}`}>
            <label>{t('views.video.udpPort')}</label>
            <input
              type="number"
              value={config.udp_port}
              min={RANGES.PORT.MIN}
              max={RANGES.PORT.MAX}
              onChange={(e) =>
                updateConfig((prev) => ({
                  ...prev,
                  udp_port: safeInt(e.target.value, VIDEO_DEFAULTS.UDP_PORT),
                }))
              }
              disabled={streaming}
            />
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
                value={config.multicast_port || VIDEO_DEFAULTS.MULTICAST_PORT}
                min={RANGES.PORT.MIN}
                max={RANGES.PORT.MAX}
                onChange={(e) =>
                  updateConfig((prev) => ({
                    ...prev,
                    multicast_port: safeInt(e.target.value, VIDEO_DEFAULTS.MULTICAST_PORT),
                  }))
                }
                disabled={streaming}
              />
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
              className={rtspUrlError ? 'input-error' : ''}
            />
            {rtspUrlError ? (
              <small className="field-error">{t('views.video.rtspUrlHint')}</small>
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

      <div className={`form-group auto-start-toggle ${streaming ? 'field-disabled' : ''}`}>
        <Toggle
          checked={config.auto_start || false}
          onChange={(e) => updateConfig((prev) => ({ ...prev, auto_start: e.target.checked }))}
          disabled={streaming}
          label={t('views.video.autoStart')}
        />
      </div>
    </div>
  )
}

export default NetworkSettingsCard
