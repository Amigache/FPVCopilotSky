import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'

const WebRTCLogCard = ({ webrtcStatus }) => {
  const { t } = useTranslation()
  const [isExpanded, setIsExpanded] = useState(false)
  const logEndRef = useRef(null)

  const logs = webrtcStatus?.log || []

  // Auto-scroll to bottom when expanded and new logs arrive
  useEffect(() => {
    if (isExpanded && logEndRef.current && logEndRef.current.scrollIntoView) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs.length, isExpanded])

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

  const levelIcons = {
    info: 'ℹ️',
    success: '✅',
    warning: '⚠️',
    error: '❌',
  }

  return (
    <div className="card webrtc-log-card" data-testid="webrtc-log-card">
      <div
        className="webrtc-log-header"
        onClick={() => setIsExpanded(!isExpanded)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') setIsExpanded(!isExpanded)
        }}
      >
        <h2>
          {t('views.video.webrtcLog')}
          <span className="webrtc-log-count">{logs.length}</span>
        </h2>
        <span className="webrtc-log-toggle">{isExpanded ? '▲' : '▼'}</span>
      </div>

      {isExpanded && (
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

export default WebRTCLogCard
