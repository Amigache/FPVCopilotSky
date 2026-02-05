import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useWebSocket } from '../../contexts/WebSocketContext'
import { useToast } from '../../contexts/ToastContext'
import { API_SYSTEM, API_MAVLINK, fetchWithTimeout } from '../../services/api'
import './FlightControllerView.css'

const FlightControllerView = () => {
  const { t } = useTranslation()
  const { messages } = useWebSocket()
  const { showToast } = useToast()
  const [serialPort, setSerialPort] = useState('/dev/ttyAML0')
  const [baudrate, setBaudrate] = useState('115200')
  const [isConnected, setIsConnected] = useState(false)
  const [status, setStatus] = useState(t('views.flightController.disconnected'))
  const [loading, setLoading] = useState(false)
  const [availablePorts, setAvailablePorts] = useState([])
  const [loadingPorts, setLoadingPorts] = useState(true)
  
  // Update connection status from WebSocket
  useEffect(() => {
    const mavlinkStatus = messages.mavlink_status
    if (mavlinkStatus) {
      setIsConnected(mavlinkStatus.connected)
      setStatus(mavlinkStatus.connected ? t('views.flightController.connected') : t('views.flightController.disconnected'))
    }
  }, [messages.mavlink_status, t])

  const availableBaudrates = [
    '9600',
    '19200',
    '38400',
    '57600',
    '115200',
    '230400',
    '460800',
    '921600'
  ]

  // Fetch available ports
  useEffect(() => {
    const fetchPorts = async () => {
      try {
        const response = await fetchWithTimeout(`${API_SYSTEM}/ports`)
        const data = await response.json()
        
        if (data.ports && data.ports.length > 0) {
          setAvailablePorts(data.ports)
          // Set first port as default if current selection is not in list
          if (!data.ports.find(p => p.path === serialPort)) {
            setSerialPort(data.ports[0].path)
          }
        } else {
          // Fallback to default ports if API returns empty
          setAvailablePorts([
            { path: '/dev/ttyAML0', name: 'ttyAML0' },
            { path: '/dev/ttyUSB0', name: 'ttyUSB0' }
          ])
        }
      } catch (error) {
        console.error('Error fetching ports:', error)
        // Fallback to default ports on error
        setAvailablePorts([
          { path: '/dev/ttyAML0', name: 'ttyAML0' },
          { path: '/dev/ttyUSB0', name: 'ttyUSB0' }
        ])
      } finally {
        setLoadingPorts(false)
      }
    }

    fetchPorts()
  }, [])

  const handleConnect = async () => {
    setLoading(true)
    showToast(t('views.flightController.connecting'), 'info')
    try {
      const response = await fetchWithTimeout(`${API_MAVLINK}/connect`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          port: serialPort,
          baudrate: parseInt(baudrate)
        })
      }, 30000)

      const data = await response.json()
      
      if (data.success) {
        setIsConnected(true)
        setStatus(t('views.flightController.connected'))
        showToast(t('views.flightController.connectSuccess'), 'success')
      } else {
        setStatus(data.message || 'Connection failed')
        showToast(`${t('views.flightController.connectError')}: ${data.message || 'Connection failed'}`, 'error')
      }
    } catch (error) {
      console.error('Error connecting:', error)
      setStatus('Error: ' + error.message)
      showToast(`${t('views.flightController.connectError')}: ${error.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleDisconnect = async () => {
    setLoading(true)
    showToast(t('views.flightController.disconnecting'), 'info')
    try {
      const response = await fetchWithTimeout(`${API_MAVLINK}/disconnect`, {
        method: 'POST'
      })

      const data = await response.json()
      
      if (data.success) {
        setIsConnected(false)
        setStatus(t('views.flightController.disconnected'))
        showToast(t('views.flightController.disconnectSuccess'), 'success')
      } else {
        showToast(t('views.flightController.disconnectError'), 'error')
      }
    } catch (error) {
      console.error('Error disconnecting:', error)
      setStatus('Error: ' + error.message)
      showToast(`${t('views.flightController.disconnectError')}: ${error.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card">
      <h2>{t('views.flightController.title')}</h2>
      
      <div className="connection-grid">
        <div className="form-group">
          <label>{t('views.flightController.serialPort')}</label>
          <select 
            value={serialPort} 
            onChange={(e) => setSerialPort(e.target.value)}
            disabled={isConnected || loading || loadingPorts}
          >
            {loadingPorts ? (
              <option>{t('views.flightController.loadingPorts')}</option>
            ) : availablePorts.length === 0 ? (
              <option>{t('views.flightController.noPortsAvailable')}</option>
            ) : (
              availablePorts.map(port => (
                <option key={port.path} value={port.path}>
                  {port.path} ({port.name})
                </option>
              ))
            )}
          </select>
        </div>

        <div className="form-group">
          <label>{t('views.flightController.baudrate')}</label>
          <select 
            value={baudrate} 
            onChange={(e) => setBaudrate(e.target.value)}
            disabled={isConnected || loading}
          >
            {availableBaudrates.map(rate => (
              <option key={rate} value={rate}>
                {rate} {rate === '115200' ? '(Recomendado)' : ''}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="button-group">
        {!isConnected ? (
          <button 
            onClick={handleConnect} 
            disabled={loading}
            className="btn-connect"
          >
            🔗 {t('views.flightController.connect')}
          </button>
        ) : (
          <button 
            onClick={handleDisconnect} 
            disabled={loading}
            className="btn-disconnect"
          >
            🔌 {t('views.flightController.disconnect')}
          </button>
        )}
      </div>

    </div>
  )
}

export default FlightControllerView
