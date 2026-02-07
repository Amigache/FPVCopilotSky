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
  const [services, setServices] = useState([])
  const [servicesLoading, setServicesLoading] = useState(true)
  const [cpuInfo, setCpuInfo] = useState(null)
  const [memoryInfo, setMemoryInfo] = useState(null)
  const [boardInfo, setBoardInfo] = useState(null)
  const [boardLoading, setBoardLoading] = useState(true)

  // Load initial status
  useEffect(() => {
    loadStatus()
    loadServices()
    loadResources()
    loadBoard()
    // No polling needed - all updates come via WebSocket
  }, [])

  // Update from WebSocket
  useEffect(() => {
    if (messages.status) {
      setStatusData(messages.status)
      setLoading(false)
    }
  }, [messages.status])

  // Update resources from WebSocket
  useEffect(() => {
    if (messages.system_resources) {
      setCpuInfo(messages.system_resources.cpu)
      setMemoryInfo(messages.system_resources.memory)
    }
  }, [messages.system_resources])

  // Update services from WebSocket
  useEffect(() => {
    if (messages.system_services) {
      setServices(messages.system_services.services || [])
      setServicesLoading(false)
    }
  }, [messages.system_services])

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

  const loadServices = async () => {
    try {
      const response = await api.get('/api/system/services')
      if (response.ok) {
        const data = await response.json()
        setServices(data.services || [])
      }
    } catch (error) {
      console.error('Error loading services:', error)
    } finally {
      setServicesLoading(false)
    }
  }

  const loadResources = async () => {
    try {
      const response = await api.get('/api/system/resources')
      if (response.ok) {
        const data = await response.json()
        setCpuInfo(data.cpu)
        setMemoryInfo(data.memory)
      }
    } catch (error) {
      console.error('Error loading resources:', error)
    }
  }

  const loadBoard = async () => {
    try {
      const response = await api.get('/api/system/board')
      if (response.ok) {
        const data = await response.json()
        setBoardInfo(data)
      }
    } catch (error) {
      console.error('Error loading board info:', error)
    } finally {
      setBoardLoading(false)
    }
  }

  // Color helpers
  const getUsageColor = (percent) => {
    if (percent >= 90) return { border: 'rgba(244, 67, 54, 0.5)', bg: 'rgba(244, 67, 54, 0.25)', text: '#ffb3b8', bar: '#f44336', barGradient: '#d32f2f' }
    if (percent >= 70) return { border: 'rgba(255, 152, 0, 0.5)', bg: 'rgba(255, 152, 0, 0.25)', text: '#ffcc80', bar: '#ff9800', barGradient: '#f57c00' }
    return { border: 'rgba(76, 175, 80, 0.5)', bg: 'rgba(76, 175, 80, 0.25)', text: '#9fe8c2', bar: '#4caf50', barGradient: '#388e3c' }
  }

  const getTempColor = (temp) => {
    if (temp >= 80) return '#f44336'
    if (temp >= 60) return '#ff9800'
    return '#4caf50'
  }

  if (loading) {
    return (
      <div className="card">
        <h2>{t('status.sections.system')}</h2>
        <div className="waiting-data">
          <div className="spinner-small"></div>
          {t('common.loadingContent', 'Cargando contenido')}
        </div>
      </div>
    )
  }

  if (!statusData) {
    return (
      <div className="card">
        <h2>{t('status.sections.system')}</h2>
        <div className="waiting-data">
          <div className="spinner-small"></div>
          {t('common.loadingContent', 'Cargando contenido')}
        </div>
      </div>
    )
  }

  const { backend } = statusData
  const connectedColor = 'rgba(102, 102, 102, 0.3)'
  const boardData = boardInfo?.data
  
  // Memory colors
  const memPercent = memoryInfo?.percentage || 0
  const memColors = getUsageColor(memPercent)
  
  // CPU colors
  const cpuPercent = cpuInfo?.usage_percent || 0
  const cpuColors = getUsageColor(cpuPercent)

  const InfoRow = ({ label, value }) => (
    <div className="info-row">
      <span className="info-label">{label}:</span>
      <span className="info-value">{value}</span>
    </div>
  )

  return (
    <div className="monitor-columns">
      <div className="monitor-col">
        {/* System Info Card */}
        <div className="card">
          <h2>🖥️ {t('status.sections.system')}</h2>
          <div className="info-section">
            <InfoRow label={t('status.system.platform')} value={backend?.system?.system?.platform || 'N/A'} />
            <InfoRow label={t('status.system.hostname')} value={backend?.system?.system?.hostname || 'N/A'} />
            <InfoRow label={t('status.system.architecture')} value={backend?.system?.system?.architecture || 'N/A'} />
            <InfoRow label={t('status.system.pythonVersion')} value={backend?.system?.system?.python_version || 'N/A'} />
          </div>
        </div>

        {/* Board Info Card */}
        <div className="card">
          <h2>🧩 {t('views.system.board', 'Board')}</h2>
          {boardLoading ? (
            <div className="waiting-data">{t('common.loading', 'Cargando')}</div>
          ) : boardInfo?.success && boardData ? (
            <div className="info-section">
              <InfoRow label={t('views.system.boardName', 'Board')} value={boardData.board_name || 'N/A'} />
              <InfoRow label={t('views.system.boardModel', 'Model')} value={boardData.board_model || 'N/A'} />
              <InfoRow label={t('views.system.cpuModel', 'CPU')} value={boardData.hardware?.cpu_model || 'N/A'} />
              <InfoRow label={t('views.system.cpuCores', 'Cores')} value={boardData.hardware?.cpu_cores ?? 'N/A'} />
              <InfoRow label={t('views.system.ram', 'RAM')} value={boardData.hardware?.ram_gb ? `${boardData.hardware.ram_gb} GB` : 'N/A'} />
              <InfoRow label={t('views.system.storage', 'Storage')} value={boardData.hardware?.storage_gb ? `${boardData.hardware.storage_gb} GB` : 'N/A'} />
              <InfoRow label={t('views.system.storageType', 'Storage Type')} value={boardData.variant?.storage_type || 'N/A'} />
              <InfoRow label={t('views.system.distro', 'Distro')} value={boardData.variant?.distro || 'N/A'} />
              <InfoRow label={t('views.system.kernel', 'Kernel')} value={boardData.variant?.kernel || 'N/A'} />
              <div className="board-features">
                <div className="board-feature-group">
                  <div className="board-feature-label">{t('views.system.videoSources', 'Video Sources')}</div>
                  <div className="board-feature-tags">
                    {(boardData.features?.video_sources || []).map((feature) => (
                      <span key={`vs-${feature}`} className="board-tag">{feature}</span>
                    ))}
                  </div>
                </div>
                <div className="board-feature-group">
                  <div className="board-feature-label">{t('views.system.videoEncoders', 'Video Encoders')}</div>
                  <div className="board-feature-tags">
                    {(boardData.features?.video_encoders || []).map((feature) => (
                      <span key={`ve-${feature}`} className="board-tag">{feature}</span>
                    ))}
                  </div>
                </div>
                <div className="board-feature-group">
                  <div className="board-feature-label">{t('views.system.connectivity', 'Connectivity')}</div>
                  <div className="board-feature-tags">
                    {(boardData.features?.connectivity || []).map((feature) => (
                      <span key={`conn-${feature}`} className="board-tag">{feature}</span>
                    ))}
                  </div>
                </div>
                <div className="board-feature-group">
                  <div className="board-feature-label">{t('views.system.systemFeatures', 'System Features')}</div>
                  <div className="board-feature-tags">
                    {(boardData.features?.system_features || []).map((feature) => (
                      <span key={`sys-${feature}`} className="board-tag">{feature}</span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="waiting-data">{boardInfo?.message || t('views.system.boardUnknown', 'No board detected')}</div>
          )}
        </div>

      </div>

      <div className="monitor-col">
        {/* Memory Card */}
        <div className="card">
          <h2>💾 {t('views.system.memory')}</h2>
          <div style={{background: 'linear-gradient(135deg, rgba(45, 45, 63, 0.4), rgba(30, 30, 46, 0.4))', border: `1px solid ${memColors.border}`, borderRadius: '4px', padding: '12px 15px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)'}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px'}}>
              <span style={{fontSize: '0.9em', fontWeight: '600', color: '#d5ddff'}}>{t('views.system.usage')}</span>
              <span style={{display: 'inline-block', padding: '3px 8px', background: memColors.bg, color: memColors.text, borderRadius: '3px', fontSize: '0.9em', fontWeight: '700', border: `1px solid ${memColors.border}`}}>
                {memPercent}%
              </span>
            </div>
            <div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', fontSize: '0.85em'}}>
              <div>
                <div style={{color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px'}}>{t('views.system.used')}</div>
                <div style={{color: '#d5ddff', fontWeight: '600'}}>{memoryInfo?.used_mb || 0} MB</div>
              </div>
              <div>
                <div style={{color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px'}}>{t('views.system.available')}</div>
                <div style={{color: '#d5ddff', fontWeight: '600'}}>{memoryInfo?.available_mb || 0} MB</div>
              </div>
              <div>
                <div style={{color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px'}}>{t('views.system.total')}</div>
                <div style={{color: '#d5ddff', fontWeight: '600'}}>{memoryInfo?.total_mb || 0} MB</div>
              </div>
            </div>
            <div style={{marginTop: '10px', background: 'rgba(20, 20, 30, 0.5)', borderRadius: '3px', height: '6px', overflow: 'hidden'}}>
              <div style={{background: `linear-gradient(90deg, ${memColors.bar}, ${memColors.barGradient})`, height: '100%', width: `${memPercent}%`, transition: 'width 0.3s'}}></div>
            </div>
          </div>
        </div>

        {/* CPU Card */}
        <div className="card">
          <h2>⚡ {t('views.system.cpu')}</h2>
          <div style={{background: 'linear-gradient(135deg, rgba(45, 45, 63, 0.4), rgba(30, 30, 46, 0.4))', border: `1px solid ${cpuColors.border}`, borderRadius: '4px', padding: '12px 15px', boxShadow: '0 1px 3px rgba(0,0,0,0.1)'}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px'}}>
              <span style={{fontSize: '0.9em', fontWeight: '600', color: '#d5ddff'}}>{t('views.system.usage')}</span>
              <span style={{display: 'inline-block', padding: '3px 8px', background: cpuColors.bg, color: cpuColors.text, borderRadius: '3px', fontSize: '0.9em', fontWeight: '700', border: `1px solid ${cpuColors.border}`}}>
                {cpuPercent}%
              </span>
            </div>
            <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(80px, 1fr))', gap: '8px', fontSize: '0.85em'}}>
              <div>
                <div style={{color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px'}}>{t('views.system.cores')}</div>
                <div style={{color: '#d5ddff', fontWeight: '600'}}>{cpuInfo?.cores || 0}</div>
              </div>
              <div>
                <div style={{color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px'}}>{t('views.system.frequency')}</div>
                <div style={{color: '#d5ddff', fontWeight: '600'}}>{cpuInfo?.frequency_mhz || '-'} MHz</div>
              </div>
              <div>
                <div style={{color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px'}}>{t('views.system.temperature')}</div>
                <div style={{color: getTempColor(cpuInfo?.temperature || 0), fontWeight: '700'}}>
                  {cpuInfo?.temperature ? `${cpuInfo.temperature}°C` : '-'}
                </div>
              </div>
              <div>
                <div style={{color: '#9aa6c3', fontSize: '0.85em', marginBottom: '2px'}}>{t('views.system.loadAvg')}</div>
                <div style={{color: '#d5ddff', fontWeight: '600', fontSize: '0.9em'}}>
                  {cpuInfo?.load_avg_1m || 0} / {cpuInfo?.load_avg_5m || 0}
                </div>
              </div>
            </div>
            <div style={{marginTop: '10px', background: 'rgba(20, 20, 30, 0.5)', borderRadius: '3px', height: '6px', overflow: 'hidden'}}>
              <div style={{background: `linear-gradient(90deg, ${cpuColors.bar}, ${cpuColors.barGradient})`, height: '100%', width: `${cpuPercent}%`, transition: 'width 0.3s'}}></div>
            </div>
          </div>
        </div>

        {/* Services Card */}
        <div className="card">
          <h2>🔧 {t('views.system.services')}</h2>
          {servicesLoading ? (
            <div className="waiting-data">{t('common.loading')}</div>
          ) : (
            <div className="services-list">
              {services.map((service) => (
                <div key={service.name} className={`service-item ${service.active ? 'active' : 'inactive'}`}>
                  <div className="service-header">
                    <span className="service-status-icon">
                      {service.active ? '🟢' : '🔴'}
                    </span>
                    <span className="service-name">{service.name}</span>
                    <span className={`service-status ${service.active ? 'running' : 'stopped'}`}>
                      {service.active ? t('views.system.running') : t('views.system.stopped')}
                    </span>
                  </div>
                  {service.active && (
                    <div className="service-details">
                      {service.memory && (
                        <span className="service-resource">
                          💾 {service.memory}
                        </span>
                      )}
                      {service.cpu_percent !== null && service.cpu_percent !== undefined && (
                        <span className="service-resource">
                          ⚡ {service.cpu_percent}%
                        </span>
                      )}
                      {service.pid && (
                        <span className="service-resource service-pid">
                          PID: {service.pid}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default SystemView
