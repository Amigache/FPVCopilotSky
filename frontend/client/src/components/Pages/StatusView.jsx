import './StatusView.css'
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../../contexts/ToastContext'
import { useModal } from '../../contexts/ModalContext'
import { useWebSocket } from '../../contexts/WebSocketContext'
import LogsModal from '../LogsModal/LogsModal'
import api from '../../services/api'
import Toggle from '../Toggle/Toggle'

const StatusView = () => {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { showModal } = useModal()
  const { messages, isConnected } = useWebSocket()
  
  const [loading, setLoading] = useState(true)
  const [statusData, setStatusData] = useState(null)
  const [resettingPrefs, setResettingPrefs] = useState(false)
  
  // Flight session state
  const [flightSession, setFlightSession] = useState(null)
  const [samplingInterval, setSamplingInterval] = useState(null)
  const [autoStartOnArm, setAutoStartOnArm] = useState(false)
  const [savingPrefs, setSavingPrefs] = useState(false)
  
  // Track previous armed state for edge detection
  const [prevArmed, setPrevArmed] = useState(false)
  
  // Logs state
  const [showLogsModal, setShowLogsModal] = useState(false)
  const [logsType, setLogsType] = useState('backend') // 'backend' or 'frontend'
  
  // Restarting state
  const [isRestarting, setIsRestarting] = useState(false)
  const [restartingService, setRestartingService] = useState('') // 'backend' or 'frontend'
  const [wasDisconnected, setWasDisconnected] = useState(false)

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

  // Update from WebSocket
  useEffect(() => {
    if (messages.status) {
      setStatusData(messages.status)
      setLoading(false)
    }
  }, [messages.status])

  // Monitor WebSocket connection during restart
  useEffect(() => {
    if (isRestarting) {
      if (!isConnected) {
        // Connection lost - expected during backend restart
        setWasDisconnected(true)
      } else if (wasDisconnected) {
        // Connection restored after being lost - restart complete
        setIsRestarting(false)
        setWasDisconnected(false)
        showToast(
          restartingService === 'backend' 
            ? t('status.restart.backendRestarted')
            : t('status.restart.frontendRestarted'), 
          'success'
        )
        setRestartingService('')
      }
    }
  }, [isConnected, isRestarting, wasDisconnected, restartingService, showToast, t])

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
          
          if (response.ok && data.success) {
            showToast(t('status.preferences.resetSuccess'), 'success')
          } else {
            showToast(data.detail || data.message || t('status.preferences.resetError'), 'error')
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

  const handleRestartBackend = () => {
    showModal({
      title: t('status.restart.confirmBackendTitle'),
      message: t('status.restart.confirmBackendMessage'),
      type: 'confirm',
      confirmText: t('status.restart.confirmButton'),
      cancelText: t('common.cancel'),
      onConfirm: async () => {
        try {
          setIsRestarting(true)
          setRestartingService('backend')
          setWasDisconnected(false)
          
          await api.restartBackend()
          // Don't show toast here - wait for reconnection
        } catch (error) {
          console.error('Error restarting backend:', error)
          // If request fails, still show restarting modal - backend may be restarting
          // The modal will close when WebSocket reconnects
        }
      }
    })
  }

  const handleRestartFrontend = () => {
    showModal({
      title: t('status.restart.confirmFrontendTitle'),
      message: t('status.restart.confirmFrontendMessage'),
      type: 'confirm',
      confirmText: t('status.restart.confirmButton'),
      cancelText: t('common.cancel'),
      onConfirm: async () => {
        try {
          setIsRestarting(true)
          setRestartingService('frontend')
          setWasDisconnected(false)
          
          await api.restartFrontend()
          // Don't show toast here - wait for reconnection
        } catch (error) {
          console.error('Error restarting frontend:', error)
          // If request fails, still show restarting modal - nginx may be restarting
          // The modal will close when WebSocket reconnects
        }
      }
    })
  }

  // Flight session handlers
  const loadFlightSession = async () => {
    try {
      const response = await api.get('/api/network/hilink/flight-session')
      if (response.ok) {
        const data = await response.json()
        setFlightSession(data)
      }
    } catch (error) {
      console.error('Error loading flight session:', error)
    }
  }

  const loadFlightPreferences = async () => {
    try {
      const response = await api.get('/api/system/preferences')
      if (response.ok) {
        const data = await response.json()
        if (data.flight_session) {
          setAutoStartOnArm(data.flight_session.auto_start_on_arm || false)
        }
      }
    } catch (error) {
      console.error('Error loading flight preferences:', error)
    }
  }

  const handleToggleAutoStart = async (enabled) => {
    setSavingPrefs(true)
    // Update state immediately for responsive UI and auto-start to work
    setAutoStartOnArm(enabled)
    
    try {
      const response = await api.post('/api/system/preferences', {
        flight_session: {
          auto_start_on_arm: enabled
        }
      })
      if (response.ok) {
        showToast(
          enabled 
            ? t('status.flightSession.autoStartEnabled', 'Auto-start enabled')
            : t('status.flightSession.autoStartDisabled', 'Auto-start disabled'),
          'success'
        )
      } else {
        // If save failed, revert the state
        setAutoStartOnArm(!enabled)
        showToast(t('common.saveFailed', 'Failed to save preferences'), 'error')
      }
    } catch (error) {
      // If request failed, revert the state
      setAutoStartOnArm(!enabled)
      showToast(error.message, 'error')
    }
    setSavingPrefs(false)
  }

  const handleStartFlightSession = async () => {
    try {
      const response = await api.post('/api/network/hilink/flight-session/start')
      if (response.ok) {
        showToast(t('status.flightSession.started', 'Flight session started'), 'success')
        await loadFlightSession()
        
        // Sample every 5 seconds
        const interval = setInterval(async () => {
          try {
            const sampleResponse = await api.post('/api/network/hilink/flight-session/sample')
            if (sampleResponse.ok) {
              await loadFlightSession()
            }
          } catch (error) {
            console.error('Error sampling:', error)
          }
        }, 5000)
        
        setSamplingInterval(interval)
      }
    } catch (error) {
      showToast(error.message, 'error')
    }
  }

  const handleStopFlightSession = async (autoStop = false) => {
    const stopSession = async () => {
      // Clear sampling interval
      if (samplingInterval) {
        clearInterval(samplingInterval)
        setSamplingInterval(null)
      }
      
      try {
        const response = await api.post('/api/network/hilink/flight-session/stop')
        if (response.ok) {
          const data = await response.json()
          showToast(t('status.flightSession.stopped', 'Flight session stopped'), 'success')
          
          if (data.stats && !autoStop) {
            showToast(
              `${t('status.flightSession.totalSamples', 'Total samples')}: ${data.stats.sample_count}`, 
              'info'
            )
          }
          await loadFlightSession()
        }
      } catch (error) {
        setFlightSession({ active: false })
        showToast(error.message, 'error')
      }
    }

    if (autoStop) {
      // Auto-stop (on disarm) - no modal confirmation
      await stopSession()
    } else {
      // Manual stop - show confirmation modal
      showModal({
        title: t('status.flightSession.confirmStopTitle', 'Stop Flight Session?'),
        message: t('status.flightSession.confirmStopMessage', 'Do you want to stop the current flight session?'),
        type: 'confirm',
        confirmText: t('common.stop', 'Stop'),
        cancelText: t('common.cancel'),
        onConfirm: stopSession
      })
    }
  }

  // Load initial status
  useEffect(() => {
    loadStatus()
    loadFlightSession()
    loadFlightPreferences()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Cleanup sampling interval on unmount
  useEffect(() => {
    return () => {
      if (samplingInterval) {
        clearInterval(samplingInterval)
      }
    }
  }, [samplingInterval])

  // Monitor armed state for auto-start
  useEffect(() => {
    const telemetry = messages.telemetry
    if (telemetry?.system) {
      const isArmed = telemetry.system.armed || false

      // Debug log
      if (isArmed !== prevArmed) {
        console.log(`[Auto-start] Armed state changed: ${prevArmed} -> ${isArmed}, autoStartOnArm=${autoStartOnArm}, sessionActive=${flightSession?.active}`)
      }

      // Detect arm transition (false -> true)
      if (autoStartOnArm && !prevArmed && isArmed && !flightSession?.active) {
        console.log('[Auto-start] Conditions met, starting flight session...')
        handleStartFlightSession()
      }

      // Detect disarm transition (true -> false)
      if (prevArmed && !isArmed && flightSession?.active) {
        console.log('[Auto-start] Drone disarmed, stopping flight session...')
        handleStopFlightSession(true)
      }

      setPrevArmed(isArmed)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages.telemetry, autoStartOnArm, flightSession])

  // Logs handlers
  const openLogsModal = (type) => {
    setLogsType(type)
    setShowLogsModal(true)
  }

  const closeLogsModal = () => {
    setShowLogsModal(false)
  }

  const fetchLogs = async () => {
    try {
      const data = logsType === 'backend' 
        ? await api.getBackendLogs(200)
        : await api.getFrontendLogs(200)
      
      if (data.success) {
        return data.logs
      } else {
        return data.message || t('status.logs.loadError')
      }
    } catch (error) {
      console.error('Error loading logs:', error)
      return t('status.logs.loadError')
    }
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
            <InfoRow
              label={t('status.system.pythonVersion')}
              value={backend?.system?.system?.python_version || 'N/A'}
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

          <div className="info-section">
            <div className="system-controls">
              <button 
                className="btn-restart-backend"
                onClick={handleRestartBackend}
              >
                🔄 {t('status.restart.restartBackend')}
              </button>
              
              <button 
                className="btn-view-logs"
                onClick={() => openLogsModal('backend')}
              >
                📜 {t('status.logs.viewBackend')}
              </button>
            </div>
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
            <InfoRow
              label={t('status.frontend.nodeVersion')}
              value={frontend?.node_version?.status === 'ok' ? `v${frontend?.node_version?.version}` : frontend?.node_version?.version || 'unknown'}
              status={frontend?.node_version?.status}
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

          <div className="info-section">
            <div className="system-controls">
              <button 
                className="btn-restart-frontend"
                onClick={handleRestartFrontend}
              >
                🌐 {t('status.restart.restartFrontend')}
              </button>
              
              <button 
                className="btn-view-logs"
                onClick={() => openLogsModal('frontend')}
              >
                📄 {t('status.logs.viewFrontend')}
              </button>
            </div>
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

        {/* Flight Session */}
        <div className="card">
          <h2>✈️ {t('status.sections.flightSession', 'Flight Session')}</h2>
          
          <div className="info-section">
            <p className="flight-session-info">
              {t('status.flightSession.description', 'Record network metrics during flight for analysis and optimization.')}
            </p>
            
            {/* Auto-start on arm toggle */}
            <div className="preference-item">
              <Toggle
                checked={autoStartOnArm}
                onChange={(e) => handleToggleAutoStart(e.target.checked)}
                disabled={savingPrefs || flightSession?.active}
                label={t('status.flightSession.autoStartLabel', 'Auto-start on arm')}
              />
              <p className="preference-description">
                {t('status.flightSession.autoStartDescription', 'Session will automatically start when vehicle is armed and stop when disarmed.')}
              </p>
            </div>
            
            {flightSession?.active ? (
              <div className="flight-session-active">
                <div className="session-status">
                  <span className="recording-indicator">🔴</span>
                  <span className="session-text">
                    {t('status.flightSession.recording', 'Recording')} - {flightSession.stats?.sample_count || 0} {t('status.flightSession.samples', 'samples')}
                  </span>
                </div>
                {!autoStartOnArm && (
                  <button className="btn-stop-session" onClick={handleStopFlightSession}>
                    ⏹️ {t('common.stop', 'Stop')}
                  </button>
                )}
              </div>
            ) : (
              !autoStartOnArm && (
                <div className="flight-session-inactive">
                  <button className="btn-start-session" onClick={handleStartFlightSession}>
                    ▶️ {t('common.start', 'Start')}
                  </button>
                </div>
              )
            )}
          </div>
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

      {/* Logs Modal */}
      <LogsModal 
        show={showLogsModal}
        onClose={closeLogsModal}
        type={logsType}
        onRefresh={fetchLogs}
      />

      {/* Restarting Modal */}
      {isRestarting && (
        <div className="logs-modal-overlay">
          <div className="restarting-modal">
            <div className="restarting-content">
              <div className="restarting-spinner"></div>
              <h3>{t('status.restart.restarting')}</h3>
              <p>
                {restartingService === 'backend' 
                  ? t('status.restart.waitingBackend')
                  : t('status.restart.waitingFrontend')}
              </p>
              {wasDisconnected && (
                <p className="restarting-status">
                  {t('status.restart.reconnecting')}
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default StatusView
