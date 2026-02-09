import { useTranslation } from 'react-i18next'

const StatusBanner = ({ status, config }) => {
  const { t } = useTranslation()

  return (
    <div
      className={`status-banner ${status.streaming ? 'streaming' : 'stopped'}`}
      data-testid="status-banner"
    >
      <div className="status-indicator">
        <span className={`status-dot ${status.streaming ? 'live' : ''}`}></span>
        <span className="status-text">
          {status.streaming ? t('views.video.streaming') : t('views.video.stopped')}
        </span>
      </div>
      {status.streaming && (
        <div className="status-info">
          {config.codec.toUpperCase()} • {config.width}x{config.height} •{' '}
          {config.mode === 'udp' && `${config.udp_host}:${config.udp_port}`}
          {config.mode === 'multicast' && `📡 ${config.multicast_group}:${config.multicast_port}`}
          {config.mode === 'rtsp' && `📡 RTSP Server`}
        </div>
      )}
      {status.last_error && <div className="status-error">❌ {status.last_error}</div>}
    </div>
  )
}

export default StatusBanner
