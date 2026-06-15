import './Header.css'
import Badge from '../Badge/Badge'
import { useTranslation } from 'react-i18next'
import { useWebSocket } from '../../contexts/WebSocketContext'
import { useParamCache } from '../../contexts/ParamCacheContext'

const Header = () => {
  const { t } = useTranslation()
  const { messages } = useWebSocket()
  const { isDownloading, status } = useParamCache()

  const mavlinkStatus = messages.mavlink_status || {
    connected: false,
    port: '',
    baudrate: 0,
  }

  const telemetry = messages.telemetry || {
    system: { armed: false, mode: 'UNKNOWN' },
  }

  const videoStatus = messages.video_status || {
    streaming: false,
  }

  const vpnStatus = messages.vpn_status || {
    connected: false,
    authenticated: false,
    installed: true,
  }

  const networkStatus = messages.network_status || {
    mode: 'unknown',
    wifi_interface: null,
    modem_interface: null,
  }

  const isArmed = telemetry.system?.armed || false
  const isStreaming = videoStatus.streaming || false
  const isVpnConnected = vpnStatus.connected || false
  const isVpnAuthenticated = vpnStatus.authenticated || false
  const isVpnInstalled = vpnStatus.installed !== false
  const networkMode = networkStatus.mode || 'unknown'

  // VPN badge logic:
  // - Connected = success (green)
  // - Authenticated but not connected = danger (red) - can be brought up
  // - Not installed or not authenticated = warning (yellow)
  const vpnBadgeVariant = isVpnConnected
    ? 'success'
    : isVpnInstalled && isVpnAuthenticated
      ? 'danger'
      : 'warning'

  return (
    <div className="header">
      {isDownloading && (
        <div
          className="param-download-topbar"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={status.progress || 0}
        >
          <div
            className="param-download-topbar-fill"
            style={{ width: `${Math.min(status.progress || 0, 99)}%` }}
          />
        </div>
      )}
      <div className="header-content">
        <h1 className="logo">📡 {t('header.title')}</h1>
        <div className="header-info">
          <div className="info-item-badge">
            <Badge variant={isStreaming ? 'success' : 'secondary'}>
              {isStreaming ? t('header.streamOnline') : t('header.streamOffline')}
            </Badge>
          </div>
          <div className="info-item-badge">
            <Badge variant={mavlinkStatus.connected ? 'success' : 'danger'}>
              {mavlinkStatus.connected ? t('header.fcConnected') : t('header.noFCConnection')}
            </Badge>
          </div>
          <div className="info-item-badge">
            <Badge variant={isArmed ? 'warning' : 'success'}>
              {isArmed ? t('header.armed') : t('header.disarmed')}
            </Badge>
          </div>
          <div className="info-item-badge">
            <Badge variant={vpnBadgeVariant}>
              {isVpnConnected ? t('header.vpnConnected') : t('header.vpnDisconnected')}
            </Badge>
          </div>
          <div className="info-item-badge">
            <Badge
              variant={
                networkMode === 'wifi' ? 'info' : networkMode === 'modem' ? 'success' : 'secondary'
              }
            >
              {networkMode === 'wifi'
                ? t('header.internetWifi', 'Internet: WIFI')
                : networkMode === 'modem'
                  ? t('header.internetModem', 'Internet: MÓDEM')
                  : t('header.noNetwork', 'No Network')}
            </Badge>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Header
