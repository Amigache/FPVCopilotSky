import { memo } from 'react'
import { useTranslation } from 'react-i18next'

/**
 * Format bytes to human-readable string
 */
const formatBytes = (bytes) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i]
}

/**
 * VPNPeersList - Displays VPN network peers/nodes
 */
const VPNPeersList = memo(({ peers, loadingPeers, onRefresh }) => {
  const { t } = useTranslation()

  return (
    <div className="card vpn-peers-card">
      <div className="card-header">
        <h2>🌐 {t('vpn.peersTitle')}</h2>
        <button className="vpn-btn-refresh" onClick={onRefresh} disabled={loadingPeers}>
          {loadingPeers ? '⏳' : '🔄'}
        </button>
      </div>

      {loadingPeers && peers.length === 0 ? (
        <div className="waiting-data">
          <div className="spinner-small"></div>
          {t('vpn.loadingPeers')}
        </div>
      ) : (
        <div className="peers-list">
          {peers.map((peer) => (
            <div
              key={peer.id}
              className={`peer-item ${peer.is_self ? 'peer-self' : ''} ${
                peer.online ? 'peer-online' : 'peer-offline'
              }`}
            >
              <div className="peer-header">
                <div className="peer-name">
                  {peer.is_self && '⭐ '}
                  {peer.hostname}
                </div>
                <div className={`peer-status ${peer.online ? 'status-online' : 'status-offline'}`}>
                  {peer.online ? '● Online' : '○ Offline'}
                </div>
              </div>
              <div className="peer-details">
                <div className="peer-detail">
                  <span className="peer-detail-label">IP:</span>
                  <span className="peer-detail-value">{peer.ip_addresses?.[0] || 'N/A'}</span>
                </div>
                <div className="peer-detail">
                  <span className="peer-detail-label">OS:</span>
                  <span className="peer-detail-value">{peer.os}</span>
                </div>
                {!peer.is_self && peer.rx_bytes !== undefined && (
                  <>
                    <div className="peer-detail">
                      <span className="peer-detail-label">↓ RX:</span>
                      <span className="peer-detail-value">{formatBytes(peer.rx_bytes)}</span>
                    </div>
                    <div className="peer-detail">
                      <span className="peer-detail-label">↑ TX:</span>
                      <span className="peer-detail-value">{formatBytes(peer.tx_bytes)}</span>
                    </div>
                  </>
                )}
              </div>
            </div>
          ))}
          {peers.length === 0 && !loadingPeers && (
            <div className="no-peers">{t('vpn.noPeers')}</div>
          )}
        </div>
      )}
    </div>
  )
})

VPNPeersList.displayName = 'VPNPeersList'

export default VPNPeersList
