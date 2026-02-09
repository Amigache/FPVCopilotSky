import { memo } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * VPNStatusCard - Displays VPN provider selector and connection status
 */
const VPNStatusCard = memo(
  ({
    status,
    providers,
    selectedProvider,
    isConnected,
    isInstalled,
    currentProvider,
    onProviderChange,
  }) => {
    const { t } = useTranslation()

    return (
      <div className="card">
        <h2>🔒 {t('vpn.title')}</h2>

        {/* Provider Selection */}
        <div className="form-group">
          <label>{t('vpn.provider')}</label>
          <select
            value={selectedProvider}
            onChange={(e) => onProviderChange(e.target.value)}
            disabled={isConnected}
          >
            {providers.map((provider) => (
              <option key={provider.name} value={provider.name}>
                {provider.display_name} {provider.installed ? '✓' : '(not installed)'}
              </option>
            ))}
          </select>
        </div>

        {/* Not Installed Warning */}
        {!isInstalled ? (
          <div className="warning-box">
            <div className="warning-icon">⚠️</div>
            <div className="warning-content">
              <h3>{t('vpn.notInstalled')}</h3>
              <p>{t('vpn.installInstructions')}</p>
              {currentProvider?.install_url && (
                <a
                  href={currentProvider.install_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="vpn-btn vpn-btn-link"
                >
                  {t('vpn.downloadProvider')}
                </a>
              )}
            </div>
          </div>
        ) : (
          /* Connection Status Display */
          <div
            className="vpn-status-container"
            style={{
              border: `1px solid ${
                isConnected ? 'rgba(76, 175, 80, 0.5)' : 'rgba(102, 102, 102, 0.3)'
              }`,
            }}
          >
            <div className="vpn-status-header">
              <span className="vpn-status-label">{t('vpn.status')}</span>
              <span className={`status-badge ${isConnected ? 'connected' : 'disconnected'}`}>
                {isConnected ? t('vpn.connected') : t('vpn.disconnected')}
              </span>
            </div>
            <div className="vpn-status-grid">
              {status?.ip_address && (
                <div>
                  <div className="vpn-field-label">{t('vpn.ipAddress')}</div>
                  <div className="vpn-field-value">{status.ip_address}</div>
                </div>
              )}

              {status?.hostname && (
                <div>
                  <div className="vpn-field-label">{t('vpn.hostname')}</div>
                  <div className="vpn-field-value">{status.hostname}</div>
                </div>
              )}

              {status?.interface && (
                <div>
                  <div className="vpn-field-label">{t('vpn.interface')}</div>
                  <div className="vpn-field-value">{status.interface}</div>
                </div>
              )}

              {typeof status?.peers_count === 'number' && (
                <div>
                  <div className="vpn-field-label">{t('vpn.peersCount')}</div>
                  <div className="vpn-field-value">
                    {status.online_peers} / {status.peers_count} {t('vpn.online')}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    )
  }
)

VPNStatusCard.displayName = 'VPNStatusCard'

export default VPNStatusCard
