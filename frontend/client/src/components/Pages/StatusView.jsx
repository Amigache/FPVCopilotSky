import './StatusView.css'
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../../contexts/ToastContext'
import { useModal } from '../../contexts/ModalContext'
import { useWebSocket } from '../../contexts/WebSocketContext'
import api from '../../services/api'

const StatusView = () => {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { showModal } = useModal()
  const { messages, isConnected } = useWebSocket()
  
  const [loading, setLoading] = useState(true)
  const [statusData, setStatusData] = useState(null)
  const [resettingPrefs, setResettingPrefs] = useState(false)

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

  const handleResetPreferences = () => {
    showModal({
      title: t('status.preferences.confirmTitle'),
      message: t('status.preferences.confirmMessage'),
      type: 'confirm',
      confirmText: t('status.preferences.confirmButton'),
      cancelText: t('common.cancel'),
      onConfirm: async () => {
        setResettingPrefs(true)
        try {
          const response = await api.post('/api/system/preferences/reset')
          const data = await response.json()
          
          if (data.success) {
            showToast(t('status.preferences.resetSuccess'), 'success')
          } else {
            showToast(data.message || t('status.preferences.resetError'), 'error')
          }
        } catch (error) {
          console.error('Error resetting preferences:', error)
          showToast(t('status.preferences.resetError'), 'error')
        } finally {
          setResettingPrefs(false)
        }
      }
    })
  }

  const StatusBadge = ({ status }) => {
    const statusClass = `status-indicator status-${status}`
    const icon = status === 'ok' ? '✅' : status === 'warning' ? '⚠️' : '❌'
    return <span className={statusClass}>{icon} {t(`status.badge.${status}`)}</span>
  }

  const InfoRow = ({ label, value, status }) => (
    <div className="info-row">
      <span className="info-label">{label}:</span>
      <span className="info-value">{value}</span>
      {status && <StatusBadge status={status} />}
    </div>
  )

  if (loading) {
    return (
      <div className="card">
        <h2>{t('status.sections.backend')}</h2>
        <div className="waiting-data">
          <div className="spinner-small"></div>
          {t('common.loadingContent')}
        </div>
      </div>
    )
  }

  if (!statusData) {
    return (
      <div className="card">
        <h2>{t('status.sections.backend')}</h2>
        <div className="waiting-data error">{t('status.error.loadingStatus')}</div>
      </div>
    )
  }

  const { backend, frontend, permissions } = statusData

  return (
    <div className="monitor-columns">
      <div className="monitor-col">
        {/* APP Status */}
        <div className="card">
          <h2>{t('status.sections.backend')}</h2>
          
          <div className="info-section">
            <h3 className="subsection-title">{t('status.backend.version')}</h3>
            <InfoRow 
              label={t('status.backend.appVersion')} 
              value={backend?.app_version?.status === 'ok' ? `v${backend?.app_version?.version}` : 'unknown'}
              status={backend?.app_version?.status}
            />
          </div>

          <div className="info-section">
            <h3 className="subsection-title">{t('status.backend.dependencies')}</h3>
            <InfoRow 
              label={t('status.backend.pythonDeps')} 
              value={backend?.python_deps?.status === 'ok' ? 'Installed' : 'Checking...'}
              status={backend?.python_deps?.status}
            />
            
            {backend?.python_deps?.missing && backend?.python_deps?.missing.length > 0 && (
              <div className="missing-info">
                <p className="missing-label">{t('status.backend.missingPackages')}:</p>
                <div className="package-list">
                  {backend.python_deps.missing.map(pkg => (
                    <span key={pkg} className="package-tag">{pkg}</span>
                  ))}
                </div>
              </div>
            )}

            {backend?.python_deps?.installed !== undefined && (
              <div className="progress-info">
                <span>{backend.python_deps.installed}/{backend.python_deps.total} installed</span>
              </div>
            )}
          </div>

          <div className="info-section">
            <h3 className="subsection-title">{t('status.backend.running')}</h3>
            <InfoRow 
              label={t('status.backend.backendRunning')} 
              value={backend?.running ? 'Yes' : 'No'}
              status={backend?.running ? 'ok' : 'error'}
            />
          </div>
        </div>

        {/* WebUI Status */}
        <div className="card">
          <h2>{t('status.sections.frontend')}</h2>
          
          <div className="info-section">
            <h3 className="subsection-title">{t('status.backend.version')}</h3>
            <InfoRow 
              label="WebUI Version" 
              value={frontend?.frontend_version?.status === 'ok' ? `v${frontend?.frontend_version?.version}` : 'unknown'}
              status={frontend?.frontend_version?.status}
            />
          </div>
          
          <div className="info-section">
            <h3 className="subsection-title">{t('status.frontend.dependencies')}</h3>
            <InfoRow 
              label={t('status.frontend.npmDeps')} 
              value={frontend?.npm_deps?.status === 'ok' ? 'Installed' : frontend?.npm_deps?.message || 'Checking...'}
              status={frontend?.npm_deps?.status}
            />
          </div>
        </div>
      </div>

      <div className="monitor-col">
        {/* Permissions */}
        <div className="card">
          <h2>{t('status.sections.permissions')}</h2>
          
          <div className="info-section">
            <h3 className="subsection-title">{t('status.permissions.username')}</h3>
            <div className="info-row">
              <span className="info-label">User:</span>
              <span className="info-value">{permissions?.permissions?.username || 'N/A'}</span>
            </div>
            <div className="info-row">
              <span className="info-label">UID:</span>
              <span className="info-value">{permissions?.permissions?.uid || 'N/A'}</span>
            </div>
            <div className="info-row">
              <span className="info-label">GID:</span>
              <span className="info-value">{permissions?.permissions?.gid || 'N/A'}</span>
            </div>
            <div className="info-row">
              <span className="info-label">{t('status.permissions.isRoot')}:</span>
              <span className="info-value">{permissions?.permissions?.is_root ? '✅ Yes' : '❌ No'}</span>
            </div>
          </div>

          {permissions?.permissions?.groups && (
            <div className="info-section">
              <h3 className="subsection-title">{t('status.permissions.groups')}</h3>
              <div className="group-tags">
                {permissions.permissions.groups.map(group => (
                  <span key={group} className="group-tag">{group}</span>
                ))}
              </div>
            </div>
          )}

          <div className="info-section">
            <h3 className="subsection-title">{t('status.permissions.filePermissions')}</h3>
            <div className="permission-check">
              <div className={permissions?.permissions?.can_read_opt ? 'check-ok' : 'check-fail'}>
                {permissions?.permissions?.can_read_opt ? '✅' : '❌'} {t('status.permissions.canRead')} /opt/FPVCopilotSky
              </div>
              <div className={permissions?.permissions?.can_write_opt ? 'check-ok' : 'check-fail'}>
                {permissions?.permissions?.can_write_opt ? '✅' : '❌'} {t('status.permissions.canWrite')} /opt/FPVCopilotSky
              </div>
            </div>
          </div>

          {permissions?.permissions?.sudoers && permissions.permissions.sudoers.length > 0 && (
            <div className="info-section">
              <h3 className="subsection-title">Sudo Permissions</h3>
              <div className="sudoers-list">
                {permissions.permissions.sudoers.map((item, idx) => (
                  <div key={idx} className="sudoers-item">
                    <span className="sudoers-source">{item.source}:</span>
                    <span className="sudoers-entry">{item.entry}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Preferences Management */}
        <div className="card">
          <h2>{t('status.sections.preferences')}</h2>
          
          <div className="info-section">
            <p className="preferences-info">
              {t('status.preferences.description')}
            </p>
            
            <button 
              className="btn-reset-preferences"
              onClick={handleResetPreferences}
              disabled={resettingPrefs}
            >
              {resettingPrefs ? t('status.preferences.resetting') : t('status.preferences.resetButton')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default StatusView
