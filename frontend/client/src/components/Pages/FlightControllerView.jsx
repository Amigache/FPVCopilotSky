import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useWebSocket } from '../../contexts/WebSocketContext'
import { useToast } from '../../contexts/ToastContext'
import { useModal } from '../../contexts/ModalContext'
import { API_SYSTEM, API_MAVLINK, fetchWithTimeout } from '../../services/api'
import './FlightControllerView.css'

// Base parameters (common to all vehicles)
const BASE_PARAMS = {
  RC_PROTOCOLS: {
    label: 'RC_PROTOCOLS',
    description: 'rcProtocolsDesc',
    recommended: 0,
    options: [
      { value: 0, label: '❌ Ninguno (Sin RC)' },
      { value: 1, label: '📡 All (Todos)' },
      { value: 2, label: '📻 PPM' },
      { value: 4, label: '📶 IBUS' },
      { value: 8, label: '📡 SBUS' },
      { value: 16, label: '🎮 DSM' },
      { value: 32, label: '📻 SUMD' },
      { value: 64, label: '🔵 SRXL' },
      { value: 128, label: '🔴 FPORT' },
      { value: 256, label: '🟢 CRSF' }
    ]
  },
  FS_GCS_ENABL: {
    label: 'FS_GCS_ENABLE',
    description: 'fsGcsDesc',
    recommended: 1,
    options: [
      { value: 0, label: '❌ Deshabilitado' },
      { value: 1, label: '✅ Habilitado' },
      { value: 2, label: '✅ + RTL si no RC' }
    ]
  }
}

// Vehicle-specific parameters
const VEHICLE_PARAMS = {
  plane: {
    title: '✈️ Parámetros Plane',
    params: {
      THR_FAILSAFE: {
        label: 'THR_FAILSAFE',
        description: 'thrFailsafeDesc',
        recommended: 0,
        options: [
          { value: 0, label: '❌ Deshabilitado' },
          { value: 1, label: '✅ Habilitado (RTL)' },
          { value: 2, label: '⚠️ Continue (sin throttle)' }
        ]
      }
    }
  },
  rover: {
    title: '🚗 Parámetros Rover',
    params: {
      FS_THR_ENABLE: {
        label: 'FS_THR_ENABLE',
        description: 'fsThrEnableDesc',
        recommended: 0,
        options: [
          { value: 0, label: '❌ Deshabilitado' },
          { value: 1, label: '✅ Habilitado (RTL)' },
          { value: 2, label: '⚠️ Continue (sin throttle)' }
        ]
      }
    }
  },
  copter: {
    title: '🚁 Parámetros Copter',
    params: {
      FS_THR_ENABLE: {
        label: 'FS_THR_ENABLE',
        description: 'fsThrEnableDesc',
        recommended: 0,
        options: [
          { value: 0, label: '❌ Deshabilitado' },
          { value: 1, label: '✅ Habilitado (Land)' },
          { value: 2, label: '🏠 RTL' },
          { value: 3, label: '⚠️ Land + SmartRTL' }
        ]
      },
      ARMING_CHECK: {
        label: 'ARMING_CHECK',
        description: 'armingCheckDesc',
        recommended: 65470,
        type: 'number'
      }
    },
    rcCalibration: true // Show RC calibration section
  }
}

// Stream Rate parameters (telemetry rates for 4G optimization)
const STREAM_RATE_PARAMS = {
  main: [
    { name: 'SR0_EXTRA1', label: 'EXTRA1 (Actitud)', description: 'Roll, Pitch, Yaw', recommended: 4, color: 'green' },
    { name: 'SR0_POSITION', label: 'POSITION (GPS)', description: 'Lat, Lon, Alt', recommended: 2, color: 'blue' },
    { name: 'SR0_EXTRA3', label: 'EXTRA3 (Velocidad)', description: 'Speed, Climb rate', recommended: 2, color: 'orange' },
    { name: 'SR0_EXT_STAT', label: 'EXT_STAT (Estado)', description: 'Modo, armado, batería', recommended: 2, color: 'purple' }
  ],
  advanced: [
    { name: 'SR0_RAW_CTRL', label: 'RAW_CTRL', description: 'Servo/motor outputs', recommended: 1 },
    { name: 'SR0_RC_CHAN', label: 'RC_CHAN', description: 'PWM inputs (no usado)', recommended: 1 }
  ]
}

// RC Calibration parameters (for copter)
const RC_CALIBRATION_PARAMS = [
  { channel: 1, name: 'Roll', minKey: 'RC1_MIN', maxKey: 'RC1_MAX' },
  { channel: 2, name: 'Pitch', minKey: 'RC2_MIN', maxKey: 'RC2_MAX' },
  { channel: 3, name: 'Throttle', minKey: 'RC3_MIN', maxKey: 'RC3_MAX' },
  { channel: 4, name: 'Yaw', minKey: 'RC4_MIN', maxKey: 'RC4_MAX' }
]

// Detect vehicle type from MAV_TYPE
const detectVehicleType = (mavType) => {
  if (!mavType) return null
  const type = mavType.toUpperCase()
  if (type.includes('FIXED') || type.includes('WING') || type.includes('PLANE')) return 'plane'
  if (type.includes('QUAD') || type.includes('HEXA') || type.includes('OCTO') || 
      type.includes('ROTOR') || type.includes('COPTER') || type.includes('TRI')) return 'copter'
  if (type.includes('ROVER') || type.includes('GROUND')) return 'rover'
  return null
}

const FlightControllerView = () => {
  const { t } = useTranslation()
  const { messages } = useWebSocket()
  const { showToast } = useToast()
  const { showModal } = useModal()
  const [serialPort, setSerialPort] = useState('/dev/ttyAML0')
  const [baudrate, setBaudrate] = useState('115200')
  const [isConnected, setIsConnected] = useState(false)
  const [_status, setStatus] = useState(t('views.flightController.disconnected'))
  const [loading, setLoading] = useState(false)
  const [availablePorts, setAvailablePorts] = useState([])
  const [loadingPorts, setLoadingPorts] = useState(true)
  const [serialPreferences, setSerialPreferences] = useState({ auto_connect: false })
  const [savingSerialPreferences, setSavingSerialPreferences] = useState(false)
  
  // Vehicle type detected from heartbeat
  const [vehicleType, setVehicleType] = useState(null)
  
  // Parameters state
  const [params, setParams] = useState({})
  const [loadingParams, setLoadingParams] = useState(false)
  const [savingParams, setSavingParams] = useState(false)
  const [paramsModified, setParamsModified] = useState({})
  const [showRcCalibration, setShowRcCalibration] = useState(false)
  const [showAdvancedStreamRates, setShowAdvancedStreamRates] = useState(false)
  
  // Update connection status and vehicle type from WebSocket
  useEffect(() => {
    const mavlinkStatus = messages.mavlink_status
    if (mavlinkStatus) {
      setIsConnected(mavlinkStatus.connected)
      setStatus(mavlinkStatus.connected ? t('views.flightController.connected') : t('views.flightController.disconnected'))
    }
    
    // Detect vehicle type from telemetry
    const telemetry = messages.telemetry
    if (telemetry?.system?.vehicle_type) {
      const detected = detectVehicleType(telemetry.system.vehicle_type)
      if (detected && detected !== vehicleType) {
        setVehicleType(detected)
      }
    }
  }, [messages.mavlink_status, messages.telemetry, t, vehicleType])

  // Auto-load parameters flag
  const [autoLoadTriggered, setAutoLoadTriggered] = useState(false)

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
    
    // Load serial preferences
    const loadSerialPreferences = async () => {
      try {
        const response = await fetchWithTimeout(`${API_MAVLINK}/preferences`)
        const data = await response.json()
        if (data.success) {
          setSerialPreferences(data.preferences || { auto_connect: false })
        }
      } catch (error) {
        console.error('Error loading serial preferences:', error)
      }
    }
    
    loadSerialPreferences()
  }, [])

  // Save serial preferences
  const saveSerialPreferences = async (newPrefs) => {
    setSavingSerialPreferences(true)
    try {
      const response = await fetchWithTimeout(`${API_MAVLINK}/preferences`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newPrefs)
      })
      const data = await response.json()
      if (data.success) {
        setSerialPreferences(data.preferences || newPrefs)
        showToast(t('views.flightController.preferencesSaved'), 'success')
      }
    } catch (error) {
      console.error('Error saving serial preferences:', error)
      showToast(t('views.flightController.preferencesError'), 'error')
    } finally {
      setSavingSerialPreferences(false)
    }
  }

  // Toggle auto-connect
  const handleAutoConnectChange = async (enabled) => {
    const newPrefs = { ...serialPreferences, auto_connect: enabled }
    setSerialPreferences(newPrefs)
    await saveSerialPreferences(newPrefs)
  }

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
      
      if (response.ok && data.success) {
        setIsConnected(true)
        setStatus(t('views.flightController.connected'))
        showToast(t('views.flightController.connectSuccess'), 'success')
      } else {
        const message = data.message || data.detail || 'Connection failed'
        setStatus(message)
        showToast(`${t('views.flightController.connectError')}: ${message}`, 'error')
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
      const notConnected = !response.ok && data.detail === 'Not connected'
      
      if (data.success || notConnected) {
        setIsConnected(false)
        setStatus(t('views.flightController.disconnected'))
        showToast(t('views.flightController.disconnectSuccess'), 'success')
        // Clear parameters when disconnected
        setParams({})
        setParamsModified({})
        setVehicleType(null)
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

  // Build list of parameters to request based on vehicle type
  const getParamsToLoad = () => {
    const paramNames = []
    
    // Base params
    Object.keys(BASE_PARAMS).forEach(p => paramNames.push(p))
    
    // Vehicle-specific params
    if (vehicleType && VEHICLE_PARAMS[vehicleType]) {
      Object.keys(VEHICLE_PARAMS[vehicleType].params).forEach(p => paramNames.push(p))
      
      // RC calibration for copter
      if (vehicleType === 'copter') {
        RC_CALIBRATION_PARAMS.forEach(rc => {
          paramNames.push(rc.minKey)
          paramNames.push(rc.maxKey)
        })
      }
    }
    
    // Stream rate params
    STREAM_RATE_PARAMS.main.forEach(sr => paramNames.push(sr.name))
    STREAM_RATE_PARAMS.advanced.forEach(sr => paramNames.push(sr.name))
    
    return paramNames
  }

  // Internal load function (with toasts for manual reload after apply recommended)
  const loadParamsInternal = async (showToasts = false) => {
    setLoadingParams(true)
    showToast('🔄 ' + t('views.flightController.loadingParams'), 'info')
    try {
      const paramNames = getParamsToLoad()
      const response = await fetchWithTimeout(`${API_MAVLINK}/params/batch/get`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ params: paramNames })
      }, 60000)
      
      const data = await response.json()
      
      if (data.parameters) {
        setParams(data.parameters)
        setParamsModified({})
        
        if (showToasts) {
          const loadedCount = Object.keys(data.parameters).length
          const errorCount = data.errors?.length || 0
          
          if (errorCount > 0) {
            showToast(`${t('views.flightController.paramsLoaded')} (${loadedCount}/${loadedCount + errorCount})`, 'warning')
          } else {
            showToast(t('views.flightController.paramsLoaded'), 'success')
          }
        }
      } else if (showToasts) {
        showToast(t('views.flightController.paramsLoadError'), 'error')
      }
    } catch (error) {
      console.error('Error loading params:', error)
      if (showToasts) {
        showToast(`${t('views.flightController.paramsLoadError')}: ${error.message}`, 'error')
      }
    } finally {
      setLoadingParams(false)
    }
  }

  // Auto-load parameters when connected and vehicle type is detected
  useEffect(() => {
    // Skip if already triggered or currently loading
    if (autoLoadTriggered || loadingParams) {
      return
    }
    
    // Check conditions for auto-load: connected + vehicle type detected
    if (isConnected && vehicleType) {
      setAutoLoadTriggered(true)
      
      // Call directly - no setTimeout needed
      ;(async () => {
        try {
          const paramNames = getParamsToLoad()
          
          setLoadingParams(true)
          showToast('🔄 ' + t('views.flightController.loadingParams'), 'info')
          const response = await fetchWithTimeout(`${API_MAVLINK}/params/batch/get`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ params: paramNames })
          }, 60000)
          
          const data = await response.json()
          
          if (data.parameters) {
            setParams(data.parameters)
            setParamsModified({})
            showToast('✅ ' + t('views.flightController.paramsLoaded'), 'success')
          }
        } catch (error) {
          console.error('Auto-load failed:', error)
          showToast(t('views.flightController.paramsLoadError'), 'error')
        } finally {
          setLoadingParams(false)
        }
      })()
    }
  }, [isConnected, vehicleType])
  
  // Reset auto-load when disconnected
  useEffect(() => {
    if (!isConnected) {
      setAutoLoadTriggered(false)
      setParams({})
    }
  }, [isConnected])

  // Handle parameter change
  const handleParamChange = (paramName, value) => {
    const numValue = parseFloat(value)
    setParamsModified(prev => ({
      ...prev,
      [paramName]: numValue
    }))
  }

  // Save modified parameters
  const saveModifiedParams = async () => {
    if (Object.keys(paramsModified).length === 0) {
      showToast(t('views.flightController.noChanges'), 'info')
      return
    }
    
    setSavingParams(true)
    try {
      const response = await fetchWithTimeout(`${API_MAVLINK}/params/batch/set`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ params: paramsModified })
      }, 60000)
      
      const data = await response.json()
      
      if (data.success) {
        // Update local state with confirmed values
        const newParams = { ...params }
        for (const [key, result] of Object.entries(data.results)) {
          if (result.success) {
            newParams[key] = result.value
          }
        }
        setParams(newParams)
        setParamsModified({})
        showToast(t('views.flightController.paramsSaved'), 'success')
      } else {
        showToast(`${t('views.flightController.paramsSaveError')}: ${data.errors?.join(', ')}`, 'error')
      }
    } catch (error) {
      console.error('Error saving params:', error)
      showToast(`${t('views.flightController.paramsSaveError')}: ${error.message}`, 'error')
    } finally {
      setSavingParams(false)
    }
  }

  // Apply recommended configuration for all parameters
  const applyRecommendedConfig = () => {
    showModal({
      title: '🚀 ' + t('views.flightController.applyRecommended'),
      message: t('views.flightController.confirmApplyRecommended'),
      type: 'confirm',
      confirmText: t('views.flightController.applyRecommended'),
      cancelText: t('common.cancel'),
      onConfirm: async () => {
        // Build recommended params object
        const recommendedParams = {}
    
    // Base params
    Object.entries(BASE_PARAMS).forEach(([name, config]) => {
      recommendedParams[name] = config.recommended
    })
    
    // Vehicle-specific params
    if (vehicleType && VEHICLE_PARAMS[vehicleType]) {
      Object.entries(VEHICLE_PARAMS[vehicleType].params).forEach(([name, config]) => {
        recommendedParams[name] = config.recommended
      })
      
      // RC calibration for copter
      if (vehicleType === 'copter') {
        RC_CALIBRATION_PARAMS.forEach(rc => {
          recommendedParams[rc.minKey] = 1101
          recommendedParams[rc.maxKey] = 1901
        })
      }
    }
    
    // Stream rates
    STREAM_RATE_PARAMS.main.forEach(sr => {
      recommendedParams[sr.name] = sr.recommended
    })
    STREAM_RATE_PARAMS.advanced.forEach(sr => {
      recommendedParams[sr.name] = sr.recommended
    })
    
    setSavingParams(true)
    try {
      const response = await fetchWithTimeout(`${API_MAVLINK}/params/batch/set`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ params: recommendedParams })
      }, 60000)
      
      const data = await response.json()
      
      if (data.success) {
        showToast(t('views.flightController.recommendedApplied'), 'success')
        // Reload parameters to show updated values
        await loadParamsInternal(true)
      } else {
        showToast(`${t('views.flightController.paramsSaveError')}: ${data.errors?.join(', ')}`, 'error')
      }
    } catch (error) {
      console.error('Error applying recommended config:', error)
      showToast(`${t('views.flightController.paramsSaveError')}: ${error.message}`, 'error')
    } finally {
      setSavingParams(false)
    }
      }
    })
  }

  // Get display value for a parameter (modified or current)
  const getParamValue = (paramName) => {
    if (Object.hasOwn(paramsModified, paramName)) {
      return paramsModified[paramName]
    }
    return params[paramName] ?? ''
  }

  // Check if inputs should be disabled (no connection OR no params loaded)
  const paramsLoaded = Object.keys(params).length > 0
  const inputsDisabled = !isConnected || savingParams || loadingParams || !paramsLoaded

  // Check if parameter matches recommended value
  const isRecommendedValue = (paramName, recommended) => {
    const currentValue = params[paramName]
    if (currentValue === undefined) return null
    return Math.abs(currentValue - recommended) < 0.001
  }

  // Render a parameter input (select or number)
  const renderParamInput = (name, config, value) => {
    const recommended = config.recommended
    const isMatch = isRecommendedValue(name, recommended)
    const isModified = Object.hasOwn(paramsModified, name)
    const hasValue = value !== '' && value !== undefined
    
    return (
      <div key={name} className={`param-item ${isModified ? 'modified' : ''} ${!hasValue ? 'no-data' : ''}`}>
        <div className="param-header">
          <label>{config.label}</label>
          {isMatch !== null && (
            <span 
              className={`param-status ${isMatch ? 'ok' : 'warning'}`}
              title={isMatch 
                ? t('views.flightController.tooltipMatchesRecommended') 
                : t('views.flightController.tooltipDiffersFromRecommended', { recommended })}
            >
              {isMatch ? '✓' : '⚠'}
            </span>
          )}
        </div>
        <div className="param-input-row">
          {config.options ? (
            <select
              value={hasValue ? value : ''}
              onChange={(e) => handleParamChange(name, e.target.value)}
              disabled={inputsDisabled}
            >
              {!hasValue && <option value="">--</option>}
              {config.options.map(opt => (
                <option key={opt.value} value={opt.value}>
                  {opt.label} {opt.value === recommended ? '★' : ''}
                </option>
              ))}
            </select>
          ) : (
            <input
              type="number"
              value={hasValue ? value : ''}
              placeholder={!hasValue ? '--' : ''}
              onChange={(e) => handleParamChange(name, e.target.value)}
              disabled={inputsDisabled}
            />
          )}
        </div>
        <small className="param-description">
          {t(`views.flightController.${config.description}`) || config.description}
          <span className="param-recommended"> | Rec: {recommended}</span>
        </small>
      </div>
    )
  }

  return (
    <div className="flight-controller-view">
      {/* Connection Card */}
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

        <div className="form-group auto-start-toggle">
          <label className="toggle-label">
            <input 
              type="checkbox" 
              checked={serialPreferences.auto_connect || false}
              onChange={(e) => handleAutoConnectChange(e.target.checked)}
              disabled={savingSerialPreferences}
            />
            <span className="toggle-switch"></span>
            <span className="toggle-text">{t('views.flightController.autoConnect')}</span>
          </label>
        </div>
      </div>

      {/* Parameters Configuration - always shown */}
      <div className="params-container">
        {/* Header with buttons */}
        <div className="card params-header-card">
          <div className="card-header-row">
            <div>
              <h2>⚙️ {t('views.flightController.configTitle')}</h2>
              {vehicleType ? (
                <span className="vehicle-badge">
                  {vehicleType === 'copter' ? '🚁' : vehicleType === 'plane' ? '✈️' : '🚗'} 
                  {vehicleType.toUpperCase()}
                </span>
              ) : isConnected ? (
                <span className="vehicle-badge detecting">⏳ {t('views.flightController.detectingVehicle')}</span>
              ) : (
                <span className="vehicle-badge disconnected">⚠ {t('views.flightController.notConnected')}</span>
              )}
            </div>
            <div className="header-buttons">
              <button
                onClick={applyRecommendedConfig}
                disabled={!isConnected || savingParams || loadingParams || !paramsLoaded}
                className="btn-primary"
              >
                🚀 {t('views.flightController.applyRecommended')}
              </button>
              {Object.keys(paramsModified).length > 0 && (
                <button
                  onClick={saveModifiedParams}
                  disabled={savingParams}
                  className="btn-success"
                >
                  {savingParams ? '⏳' : '💾'} {t('views.flightController.saveChanges')} ({Object.keys(paramsModified).length})
                </button>
              )}
            </div>
          </div>
        </div>

        <div className="params-two-columns">
              {/* Left Column: Base + Vehicle-Specific */}
              <div className="params-column">
                {/* Base Parameters Card */}
                <div className="card">
                  <h3>⚙️ {t('views.flightController.baseParams')}</h3>
                  <div className="params-list">
                    {Object.entries(BASE_PARAMS).map(([name, config]) => 
                      renderParamInput(name, config, getParamValue(name))
                    )}
                  </div>
                </div>

                {/* Vehicle-Specific Parameters Card */}
                <div className="card">
                  <h3>{vehicleType ? VEHICLE_PARAMS[vehicleType]?.title : '🔧 ' + t('views.flightController.vehicleParams')}</h3>
                  {vehicleType && VEHICLE_PARAMS[vehicleType] ? (
                    <>
                      <div className="params-list">
                        {Object.entries(VEHICLE_PARAMS[vehicleType].params).map(([name, config]) => 
                          renderParamInput(name, config, getParamValue(name))
                        )}
                      </div>

                      {/* RC Calibration (Copter only) */}
                      {vehicleType === 'copter' && (
                      <details className="rc-calibration-section" open={showRcCalibration}>
                        <summary onClick={(e) => { e.preventDefault(); setShowRcCalibration(!showRcCalibration) }}>
                          ▸ {t('views.flightController.rcCalibration')}
                        </summary>
                        <div className="rc-calibration-content">
                          <p className="rc-calibration-help">{t('views.flightController.rcCalibrationDesc')}</p>
                          <div className="rc-grid">
                            {RC_CALIBRATION_PARAMS.map(rc => (
                              <div key={rc.channel} className="rc-channel">
                                <span className="rc-channel-name">RC{rc.channel} ({rc.name})</span>
                                <div className="rc-inputs">
                                  <div>
                                    <label>MIN</label>
                                    <input
                                      type="number"
                                      value={getParamValue(rc.minKey)}
                                      onChange={(e) => handleParamChange(rc.minKey, e.target.value)}
                                      disabled={inputsDisabled}
                                      placeholder="--"
                                    />
                                  </div>
                                  <div>
                                    <label>MAX</label>
                                    <input
                                      type="number"
                                      value={getParamValue(rc.maxKey)}
                                      onChange={(e) => handleParamChange(rc.maxKey, e.target.value)}
                                      disabled={inputsDisabled}
                                      placeholder="--"
                                    />
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </details>
                    )}
                    </>
                  ) : (
                    <div className="empty-vehicle-params">
                      <p>{t('views.flightController.selectVehicleType')}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Right Column: Stream Rates */}
              <div className="params-column">
                <div className="card">
                  <h3>📡 {t('views.flightController.streamRates')}</h3>
                  <p className="stream-rates-help">{t('views.flightController.streamRatesDesc')}</p>
                  
                  <div className="stream-rates-list">
                    {STREAM_RATE_PARAMS.main.map(sr => {
                      const value = getParamValue(sr.name)
                      const isMatch = isRecommendedValue(sr.name, sr.recommended)
                      const isModified = Object.hasOwn(paramsModified, sr.name)
                      
                      return (
                        <div key={sr.name} className={`stream-rate-item color-${sr.color} ${isModified ? 'modified' : ''}`}>
                          <div className="stream-rate-info">
                            <div className="stream-rate-label">{sr.label}</div>
                            <small>{sr.description}</small>
                          </div>
                          <div className="stream-rate-input">
                            <input
                              type="number"
                              value={value}
                              onChange={(e) => handleParamChange(sr.name, e.target.value)}
                            disabled={inputsDisabled}
                            min="0"
                            max="50"
                            placeholder="--"
                            />
                            <span className="hz-label">Hz</span>
                            {isMatch !== null && (
                              <span 
                                className={`param-status ${isMatch ? 'ok' : 'warning'}`}
                                title={isMatch 
                                  ? t('views.flightController.tooltipMatchesRecommended') 
                                  : t('views.flightController.tooltipDiffersFromRecommended', { recommended: sr.recommended })}
                              >
                                {isMatch ? '✓' : '⚠'}
                              </span>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  {/* Advanced Stream Rates */}
                  <details className="advanced-stream-rates" open={showAdvancedStreamRates}>
                    <summary onClick={(e) => { e.preventDefault(); setShowAdvancedStreamRates(!showAdvancedStreamRates) }}>
                      {t('views.flightController.advancedParams')}
                    </summary>
                    <div className="advanced-stream-content">
                      {STREAM_RATE_PARAMS.advanced.map(sr => {
                        const value = getParamValue(sr.name)
                        return (
                          <div key={sr.name} className="stream-rate-item advanced">
                            <div className="stream-rate-info">
                              <div className="stream-rate-label">{sr.label}</div>
                              <small>{sr.description}</small>
                            </div>
                            <div className="stream-rate-input">
                              <input
                                type="number"
                                value={value}
                                onChange={(e) => handleParamChange(sr.name, e.target.value)}
                                disabled={inputsDisabled}
                                min="0"
                                max="50"
                                placeholder="--"
                              />
                              <span className="hz-label">Hz</span>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </details>

                  <div className="info-box">
                    💡 <strong>{t('views.flightController.recommended4G')}:</strong> {t('views.flightController.recommended4GValues')}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
    )
  }

export default FlightControllerView
