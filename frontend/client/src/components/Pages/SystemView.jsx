import './SystemView.css'
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../../contexts/ToastContext'
import { useWebSocket } from '../../contexts/WebSocketContext'
import api from '../../services/api'

const SystemView = () => {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { messages } = useWebSocket()
  
  const [loading, setLoading] = useState(true)
  const [statusData, setStatusData] = useState(null)

  // Load initial status
  useEffect(() => {
    loadStatus()
  }, [])

  // Update from WebSocket
  useEffect(() => {
    if (messages.status) {
      setStatusData(messages.status)
      setLoading(false)
    }
  }, [messages.status])

  const loadStatus = async () => {
    try {
      const response = await api.get('/api/status/health')
      if (response.ok) {
        const data = await response.json()
        setStatusData(data)
      } else {
        showToast(t('status.error.loadingStatus'), 'error')
      }
    } catch (error) {
      console.error('Error loading status:', error)
      showToast(t('status.error.loadingStatus'), 'error')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="card">
        <h2>{t('status.sections.system')}</h2>
        <div className="waiting-data">{t('common.loading')}</div>
      </div>
    )
  }

  if (!statusData) {
    return (
      <div className="card">
        <h2>{t('status.sections.system')}</h2>
        <div className="waiting-data">{t('views.system.waiting')}</div>
      </div>
    )
  }

  const { backend } = statusData

  const InfoRow = ({ label, value }) => (
    <div className="info-row">
      <span className="info-label">{label}:</span>
      <span className="info-value">{value}</span>
    </div>
  )

  return (
    <div className="monitor-columns">
      <div className="monitor-col">
        <div className="card">
          <h2>🖥️ {t('status.sections.system')}</h2>
          <div className="info-section">
            <InfoRow label={t('status.system.platform')} value={backend?.system?.system?.platform || 'N/A'} />
            <InfoRow label={t('status.system.hostname')} value={backend?.system?.system?.hostname || 'N/A'} />
            <InfoRow label={t('status.system.architecture')} value={backend?.system?.system?.architecture || 'N/A'} />
            <InfoRow label={t('status.system.pythonVersion')} value={backend?.system?.system?.python_version || 'N/A'} />
          </div>
        </div>
      </div>
    </div>
  )
}

export default SystemView
