import './TelemetryView.css'
import { useTranslation } from 'react-i18next'
import { useState, useEffect, useCallback } from 'react'
import { useToast } from '../../contexts/ToastContext'
import { useModal } from '../../contexts/ModalContext'
import { useWebSocket } from '../../contexts/WebSocketContext'
import { API_MAVLINK_ROUTER, fetchWithTimeout } from '../../services/api'
import { PeerSelector } from '../PeerSelector/PeerSelector'

const TelemetryView = () => {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { showModal } = useModal()
  const { messages } = useWebSocket()
  
  // Router state
  const [outputs, setOutputs] = useState([])
  const [loading, setLoading] = useState(false)
  
  // Form state
  const [outputType, setOutputType] = useState('tcp_server')
  const [host, setHost] = useState('0.0.0.0')
  const [port, setPort] = useState('14550')
  
  // Presets
  const presets = {
    qgc_udp: { type: 'udp', host: '0.0.0.0', port: '14550' },
    mission_planner_tcp: { type: 'tcp_server', host: '0.0.0.0', port: '5760' },
    tcp_client: { type: 'tcp_client', host: '192.168.1.100', port: '5760' }
  }
  
  const fetchOutputs = useCallback(async () => {
    try {
      // Fetch router outputs
      const response = await fetchWithTimeout(`${API_MAVLINK_ROUTER}/outputs`)
      if (response.ok) {
        const data = await response.json()
        setOutputs(data)
      } else {
        console.error('Error fetching outputs: HTTP', response.status)
      }
    } catch (error) {
      console.error('Error fetching outputs:', error)
    }
  }, [])
  
  // Load outputs on mount only (updates come via WebSocket)
  useEffect(() => {
    fetchOutputs()
  }, [fetchOutputs])
  
  // Listen for router updates via WebSocket
  useEffect(() => {
    if (messages.router_status) {
      setOutputs(messages.router_status)
    }
  }, [messages.router_status])
  
  const handleCreateOutput = async (e) => {
    e.preventDefault()
    setLoading(true)
    
    try {
      const response = await fetchWithTimeout(`${API_MAVLINK_ROUTER}/outputs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: outputType,
          host: host,
          port: parseInt(port)
        })
      })
      
      if (response.ok) {
        showToast(t('router.outputCreated'), 'success')
        fetchOutputs()
      } else {
        const error = await response.json()
        showToast(error.detail || t('router.createError'), 'error')
      }
    } catch (error) {
      showToast(t('router.createError'), 'error')
      console.error('Error creating output:', error)
    } finally {
      setLoading(false)
    }
  }
  
  const handleDeleteOutput = async (outputId) => {
    const output = outputs.find(o => o.id === outputId)
    
    showModal({
      title: t('router.confirmDelete'),
      message: `${t('router.confirmDeleteMessage')} ${output?.host}:${output?.port}?`,
      type: 'confirm',
      confirmText: t('router.delete'),
      cancelText: t('router.cancel'),
      onConfirm: async () => {
        try {
          const response = await fetchWithTimeout(`${API_MAVLINK_ROUTER}/outputs/${outputId}`, {
            method: 'DELETE'
          })
          
          if (response.ok) {
            showToast(t('router.outputDeleted'), 'success')
            await fetchOutputs()
          } else {
            showToast(t('router.deleteError'), 'error')
          }
        } catch (error) {
          showToast(t('router.deleteError'), 'error')
          console.error('Error deleting output:', error)
        }
      }
    })
  }
  
  const applyPreset = (presetKey) => {
    const preset = presets[presetKey]
    setOutputType(preset.type)
    setHost(preset.host)
    setPort(preset.port.toString())
  }
  
  const getTypeLabel = (type) => {
    const labels = {
      'tcp_server': 'TCP Server',
      'tcp_client': 'TCP Client',
      'udp': 'UDP'
    }
    return labels[type] || type
  }

  return (
    <div className="telemetry-container">
      {/* MAVLink Router Card */}
      <div className="card router-card">
        <h2>📡 {t('router.title')}</h2>
        
        {/* Create Output Form */}
        <form onSubmit={handleCreateOutput} className="router-form">
          <div className="connection-grid">
            <div className="form-group">
              <label>{t('router.type')}</label>
              <select 
                value={outputType} 
                onChange={(e) => setOutputType(e.target.value)}
                disabled={loading}
              >
                <option value="tcp_server">{t('router.tcpServer')}</option>
                <option value="tcp_client">{t('router.tcpClient')}</option>
                <option value="udp">{t('router.udp')}</option>
              </select>
            </div>
            
            <div className="form-group">
              <PeerSelector
                label={t('router.host')}
                value={host}
                onChange={setHost}
                disabled={loading}
                placeholder="0.0.0.0"
              />
            </div>
            
            <div className="form-group">
              <label>{t('router.port')}</label>
              <input
                type="number"
                value={port}
                onChange={(e) => setPort(e.target.value)}
                disabled={loading}
                placeholder="14550"
                min="1"
                max="65535"
              />
            </div>
          </div>
          
          <div className="button-group">
            <button type="submit" className="btn-primary" disabled={loading}>
              ➕ {t('router.create')}
            </button>
            <button 
              type="button" 
              className="btn-secondary" 
              onClick={() => applyPreset('qgc_udp')}
              disabled={loading}
            >
              📱 {t('router.presetQGC')}
            </button>
            <button 
              type="button" 
              className="btn-secondary" 
              onClick={() => applyPreset('mission_planner_tcp')}
              disabled={loading}
            >
              🚁 {t('router.presetMP')}
            </button>
          </div>
        </form>
        
        {/* Configured Outputs */}
        {outputs.length > 0 && (
          <div className="outputs-section">
            <h3>📋 {t('router.configuredOutputs')}</h3>
            <div className="outputs-list">
              {outputs.map(output => (
                <div key={output.id} className={`output-item ${output.running ? 'active' : ''}`}>
                  <div className="output-info">
                    <span className={`status-indicator ${output.running ? 'running' : 'stopped'}`}>
                      {output.running ? '🟢' : '🔴'}
                    </span>
                    <span className="output-type">{getTypeLabel(output.type)}</span>
                    <span className="output-address">{output.host}:{output.port}</span>
                    {output.type === 'tcp_server' && (
                      <span className="client-count">
                        👥 {output.clients || 0} {t('router.clients')}
                      </span>
                    )}
                    {output.stats && (
                      <span className="output-stats">
                        📤 {output.stats.tx || 0} 📥 {output.stats.rx || 0}
                      </span>
                    )}
                  </div>
                  <div className="output-actions">
                    <button 
                      className="btn-delete" 
                      onClick={() => handleDeleteOutput(output.id)}
                    >
                      🗑 {t('router.delete')}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default TelemetryView
