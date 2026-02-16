import { useTranslation } from 'react-i18next'

const StatsCard = ({ status, webrtcVideoStats, autoAdaptiveBitrate }) => {
  const { t } = useTranslation()
  const { stats, config } = status
  const isWebRTC = config.mode === 'webrtc'

  return (
    <div className="card stats-card" data-testid="stats-card">
      <h2>{t('views.video.statistics')}</h2>

      {/* Health Indicator */}
      <div className={`health-indicator health-${stats.health}`}>
        <span className="health-dot"></span>
        <span className="health-text">{t(`views.video.health.${stats.health}`)}</span>
      </div>

      {/* Main Stats Grid */}
      <div className="stats-grid-main">
        <div className="stat-item">
          <span className="stat-label">{t('views.video.uptime')}</span>
          <span className="stat-value">{stats.uptime_formatted}</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">{t('views.video.fpsLabel')}</span>
          <span className="stat-value">
            {isWebRTC && webrtcVideoStats ? webrtcVideoStats.fps : stats.current_fps}
          </span>
          <span className="stat-unit">/{config.framerate} fps</span>
        </div>
        <div className="stat-item">
          <span className="stat-label">{t('views.video.bitrateLabel')}</span>
          <span className="stat-value">
            {isWebRTC && webrtcVideoStats ? webrtcVideoStats.bitrate : stats.current_bitrate}
            {autoAdaptiveBitrate && <span className="stat-auto-indicator"> (auto)</span>}
          </span>
          <span className="stat-unit">kbps</span>
        </div>
      </div>

      {/* Secondary Stats Grid */}
      <div className="stats-grid-secondary">
        {/* WebRTC-specific stats */}
        {isWebRTC && webrtcVideoStats ? (
          <>
            <div className="stat-item-secondary">
              <span className="stat-label">{t('views.video.webrtcResolution')}</span>
              <span className="stat-value-sm">{webrtcVideoStats.resolution || '-'}</span>
            </div>
            <div className="stat-item-secondary">
              <span className="stat-label">RTT</span>
              <span className="stat-value-sm">{webrtcVideoStats.rtt} ms</span>
            </div>
            <div className="stat-item-secondary">
              <span className="stat-label">{t('views.video.webrtcJitter')}</span>
              <span className="stat-value-sm">{webrtcVideoStats.jitter} ms</span>
            </div>
            <div className="stat-item-secondary">
              <span className="stat-label">{t('views.video.webrtcPacketsLost')}</span>
              <span
                className={`stat-value-sm ${webrtcVideoStats.packetsLost > 0 ? 'error-count' : ''}`}
              >
                {webrtcVideoStats.packetsLost}
              </span>
            </div>
            <div className="stat-item-secondary">
              <span className="stat-label">{t('views.video.webrtcPeers')}</span>
              <span className="stat-value-sm">{status.webrtc?.peers_connected || 0}</span>
            </div>
          </>
        ) : (
          <>
            <div className="stat-item-secondary">
              <span className="stat-label">{t('views.video.framesSent')}</span>
              <span className="stat-value-sm">{stats.frames_sent}</span>
            </div>
            <div className="stat-item-secondary">
              <span className="stat-label">{t('views.video.dataSent')}</span>
              <span className="stat-value-sm">{stats.bytes_sent_mb} MB</span>
            </div>
            <div className="stat-item-secondary">
              <span className="stat-label">{t('views.video.errors')}</span>
              <span className={`stat-value-sm ${stats.errors > 0 ? 'error-count' : ''}`}>
                {stats.errors}
              </span>
            </div>
            {/* RTSP Clients Counter — only in RTSP mode */}
            {config.mode === 'rtsp' && status.rtsp_server?.running && (
              <div className="stat-item-secondary">
                <span className="stat-label">{t('views.video.rtspClients')}</span>
                <span className="stat-value-sm">{status.rtsp_server.clients_connected || 0}</span>
              </div>
            )}
          </>
        )}
      </div>

      {/* Provider Info */}
      <div className="pipeline-info">
        <span className="info-label">{t('views.video.providersLabel')}</span>
        <span className="info-value">
          {status.providers?.encoder ? (
            <>
              {status.providers.encoder}
              {status.providers.source && ` (from ${status.providers.source})`}
            </>
          ) : (
            t('views.video.noProvidersActive')
          )}
        </span>
      </div>

      {/* Pipeline Info */}
      <div className="pipeline-info">
        <span className="info-label">{t('views.video.pipelineLabel')}</span>
        <span className="info-value">
          {config.codec.toUpperCase()} • {config.width}x{config.height}@{config.framerate}fps
        </span>
      </div>
      <div className="pipeline-info">
        <span className="info-label">{t('views.video.destinationLabel')}</span>
        <span className="info-value">
          {config.mode === 'udp' && `UDP ${config.udp_host}:${config.udp_port}`}
          {config.mode === 'multicast' &&
            `Multicast ${config.multicast_group}:${config.multicast_port} (TTL ${config.multicast_ttl})`}
          {config.mode === 'rtsp' && `RTSP Server → ${config.rtsp_url}`}
          {config.mode === 'webrtc' && `WebRTC (${status.webrtc?.peers_connected || 0} peers)`}
          {!config.mode && `UDP ${config.udp_host}:${config.udp_port}`}
        </span>
      </div>
    </div>
  )
}

export default StatsCard
