import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useWebSocket } from '../../../contexts/WebSocketContext'
import { useToast } from '../../../contexts/ToastContext'
import { useModal } from '../../../contexts/ModalContext'
import { API_SYSTEM, API_MAVLINK, fetchWithTimeout } from '../../../services/api'
import Toggle from '../../Toggle/Toggle'
import {
  AVAILABLE_BAUDRATES,
  DEFAULT_BAUDRATE,
  BASE_PARAMS,
  VEHICLE_PARAMS,
  STREAM_RATE_PARAMS,
  RC_CALIBRATION_PARAMS,
  detectVehicleType,
  getParamNamesToLoad,
  buildRecommendedParams,
} from './flightControllerConstants'
import './FlightControllerView.css'

const FlightControllerView = () => {
  const { t } = useTranslation()
  const { messages } = useWebSocket()
  const { showToast } = useToast()
  const { showModal } = useModal()
  const [serialPort, setSerialPort] = useState('')
  const [baudrate, setBaudrate] = useState(DEFAULT_BAUDRATE)
  const [isConnected, setIsConnected] = useState(false)
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
    }

    // Detect vehicle type from telemetry
    const telemetry = messages.telemetry
    if (telemetry?.system?.vehicle_type) {
      const detected = detectVehicleType(telemetry.system.vehicle_type)
      if (detected && detected !== vehicleType) {
        setVehicleType(detected)
      }
    }
  }, [messages.mavlink_status, messages.telemetry, vehicleType])

  // Auto-load parameters flag
  const [autoLoadTriggered, setAutoLoadTriggered] = useState(false)

  // Fetch available ports and load saved preferences on mount
  useEffect(() => {
    const fetchPorts = async () => {
      try {
        const response = await fetchWithTimeout(`${API_SYSTEM}/ports`)
        const data = await response.json()
        const ports = data.ports?.length > 0 ? data.ports : []
        setAvailablePorts(ports)
      } catch (error) {
        console.error('Error fetching ports:', error)
        setAvailablePorts([])
      } finally {
        setLoadingPorts(false)
      }
    }

    const loadSerialPreferences = async () => {
      try {
        const response = await fetchWithTimeout(`${API_MAVLINK}/preferences`)
        const data = await response.json()
        if (data.success && data.preferences) {
          setSerialPreferences(data.preferences)
          // Restore saved port and baudrate
          if (data.preferences.port) {
            setSerialPort(data.preferences.port)
          }
          if (data.preferences.baudrate) {
            setBaudrate(String(data.preferences.baudrate))
          }
        }
      } catch (error) {
        console.error('Error loading serial preferences:', error)
      }
    }

    fetchPorts()
    loadSerialPreferences()
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        body: JSON.stringify(newPrefs),
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
      const response = await fetchWithTimeout(
        `${API_MAVLINK}/connect`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            port: serialPort,
            baudrate: parseInt(baudrate),
          }),
        },
        30000
      )

      const data = await response.json()

      if (response.ok && data.success) {
        setIsConnected(true)
        showToast(t('views.flightController.connectSuccess'), 'success')
      } else {
        const message = data.message || data.detail || 'Connection failed'
        showToast(`${t('views.flightController.connectError')}: ${message}`, 'error')
      }
    } catch (error) {
      console.error('Error connecting:', error)
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
        method: 'POST',
      })

      const data = await response.json()
      const notConnected = !response.ok && data.detail === 'Not connected'

      if (data.success || notConnected) {
        setIsConnected(false)
        showToast(t('views.flightController.disconnectSuccess'), 'success')
        // Clear all parameter state on disconnect
        setParams({})
        setParamsModified({})
        setVehicleType(null)
      } else {
        showToast(t('views.flightController.disconnectError'), 'error')
      }
    } catch (error) {
      console.error('Error disconnecting:', error)
      showToast(`${t('views.flightController.disconnectError')}: ${error.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  // Internal load function (with toasts for manual reload after apply recommended)
  const loadParamsInternal = useCallback(
    async (showToasts = false) => {
      setLoadingParams(true)
      showToast('🔄 ' + t('views.flightController.loadingParams'), 'info')
      try {
        const paramNames = getParamNamesToLoad(vehicleType)
        const response = await fetchWithTimeout(
          `${API_MAVLINK}/params/batch/get`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ params: paramNames }),
          },
          60000
        )

        const data = await response.json()

        if (data.parameters) {
          setParams(data.parameters)
          setParamsModified({})

          if (showToasts) {
            const loadedCount = Object.keys(data.parameters).length
            const errorCount = data.errors?.length || 0

            if (errorCount > 0) {
              showToast(
                `${t('views.flightController.paramsLoaded')} (${loadedCount}/${
                  loadedCount + errorCount
                })`,
                'warning'
              )
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
    },
    [vehicleType, showToast, t]
  )

  // Auto-load parameters when connected and vehicle type is detected
  useEffect(() => {
    if (autoLoadTriggered || loadingParams) return
    if (isConnected && vehicleType) {
      setAutoLoadTriggered(true)
      loadParamsInternal(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isConnected, vehicleType])

  // Reset auto-load and clear params when disconnected
  useEffect(() => {
    if (!isConnected) {
      setAutoLoadTriggered(false)
      setParams({})
      setParamsModified({})
    }
  }, [isConnected])

  // Handle parameter change
  const handleParamChange = (paramName, value) => {
    if (value === '' || value === undefined || value === null) {
      // Remove from modified if cleared (revert to original)
      setParamsModified((prev) => {
        const next = { ...prev }
        delete next[paramName]
        return next
      })
      return
    }
    const numValue = parseFloat(value)
    if (Number.isNaN(numValue)) return
    setParamsModified((prev) => ({
      ...prev,
      [paramName]: numValue,
    }))
  }

  // Save modified parameters
  const saveModifiedParams = async () => {
    // Filter out any NaN or invalid values
    const validParams = {}
    for (const [key, val] of Object.entries(paramsModified)) {
      if (typeof val === 'number' && !Number.isNaN(val)) {
        validParams[key] = val
      }
    }

    if (Object.keys(validParams).length === 0) {
      showToast(t('views.flightController.noChanges'), 'info')
      return
    }

    setSavingParams(true)
    try {
      const response = await fetchWithTimeout(
        `${API_MAVLINK}/params/batch/set`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ params: validParams }),
        },
        60000
      )

      const data = await response.json()

      // Process results: update successful params and track failures
      const newParams = { ...params }
      const successfulParams = []
      const failedParams = []

      if (data.results) {
        for (const [key, result] of Object.entries(data.results)) {
          if (result.success) {
            newParams[key] = result.value
            successfulParams.push(key)
          } else {
            failedParams.push(key)
          }
        }
      }

      // Update state: remove successfully saved params from modified
      setParams(newParams)
      if (successfulParams.length > 0) {
        setParamsModified((prev) => {
          const next = { ...prev }
          successfulParams.forEach((key) => delete next[key])
          return next
        })
      }

      // Show appropriate toast based on results
      if (failedParams.length === 0) {
        showToast(t('views.flightController.paramsSaved'), 'success')
      } else if (successfulParams.length > 0) {
        showToast(
          `${t('views.flightController.paramsSaved')} (${successfulParams.length}/${
            Object.keys(validParams).length
          }). ${t('views.flightController.paramsSaveError')}: ${failedParams.join(', ')}`,
          'warning'
        )
      } else {
        showToast(
          `${t('views.flightController.paramsSaveError')}: ${
            data.errors?.join(', ') || failedParams.join(', ')
          }`,
          'error'
        )
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
        const recommendedParams = buildRecommendedParams(vehicleType)

        setSavingParams(true)
        try {
          const response = await fetchWithTimeout(
            `${API_MAVLINK}/params/batch/set`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ params: recommendedParams }),
            },
            60000
          )

          const data = await response.json()

          // Count successes and failures
          const successCount = data.results
            ? Object.values(data.results).filter((r) => r.success).length
            : 0
          const totalCount = Object.keys(recommendedParams).length
          const failedParams = data.results
            ? Object.keys(data.results).filter((key) => !data.results[key].success)
            : []

          if (failedParams.length === 0) {
            showToast(t('views.flightController.recommendedApplied'), 'success')
          } else if (successCount > 0) {
            showToast(
              `${t(
                'views.flightController.recommendedApplied'
              )} (${successCount}/${totalCount}). ${t(
                'views.flightController.paramsSaveError'
              )}: ${failedParams.join(', ')}`,
              'warning'
            )
          } else {
            showToast(
              `${t('views.flightController.paramsSaveError')}: ${
                data.errors?.join(', ') || failedParams.join(', ')
              }`,
              'error'
            )
          }

          // Always reload params to show what was actually applied
          await loadParamsInternal(true)
        } catch (error) {
          console.error('Error applying recommended config:', error)
          showToast(`${t('views.flightController.paramsSaveError')}: ${error.message}`, 'error')
        } finally {
          setSavingParams(false)
        }
      },
    })
  }

  // Get display value for a parameter (modified or current)
  const getParamValue = (paramName) => {
    if (Object.hasOwn(paramsModified, paramName)) {
      return paramsModified[paramName]
    }
    return params[paramName] ?? ''
  }

  // Count only valid modified params for the save button
  const validModifiedCount = Object.values(paramsModified).filter(
    (v) => typeof v === 'number' && !Number.isNaN(v)
  ).length

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
      <div
        key={name}
        className={`param-item ${isModified ? 'modified' : ''} ${!hasValue ? 'no-data' : ''}`}
      >
        <div className="param-header">
          <label>{config.label}</label>
          {isMatch !== null && (
            <span
              className={`param-status ${isMatch ? 'ok' : 'warning'}`}
              title={
                isMatch
                  ? t('views.flightController.tooltipMatchesRecommended')
                  : t('views.flightController.tooltipDiffersFromRecommended', { recommended })
              }
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
              {config.options.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.labelKey ? t(`views.flightController.${opt.labelKey}`) : opt.label}{' '}
                  {opt.value === recommended ? '★' : ''}
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
                availablePorts.map((port) => (
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
              {AVAILABLE_BAUDRATES.map((rate) => (
                <option key={rate} value={rate}>
                  {rate}{' '}
                  {rate === DEFAULT_BAUDRATE ? t('views.flightController.baudrateRecommended') : ''}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="connection-actions">
          <Toggle
            checked={serialPreferences.auto_connect || false}
            onChange={(e) => handleAutoConnectChange(e.target.checked)}
            disabled={savingSerialPreferences}
            label={t('views.flightController.autoConnect')}
          />
          {!isConnected ? (
            <button
              onClick={handleConnect}
              disabled={loading || !serialPort || loadingPorts}
              className="btn-connect"
            >
              🔗 {t('views.flightController.connect')}
            </button>
          ) : (
            <button onClick={handleDisconnect} disabled={loading} className="btn-disconnect">
              🔌 {t('views.flightController.disconnect')}
            </button>
          )}
        </div>
      </div>

      {/* Parameters Configuration */}
      <div className="params-container">
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
              <h3>
                {vehicleType && VEHICLE_PARAMS[vehicleType]?.titleKey
                  ? t(`views.flightController.${VEHICLE_PARAMS[vehicleType].titleKey}`)
                  : '🔧 ' + t('views.flightController.vehicleParams')}
              </h3>
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
                      <summary
                        onClick={(e) => {
                          e.preventDefault()
                          setShowRcCalibration(!showRcCalibration)
                        }}
                      >
                        ▸ {t('views.flightController.rcCalibration')}
                      </summary>
                      <div className="rc-calibration-content">
                        <p className="rc-calibration-help">
                          {t('views.flightController.rcCalibrationDesc')}
                        </p>
                        <div className="rc-grid">
                          {RC_CALIBRATION_PARAMS.map((rc) => (
                            <div key={rc.channel} className="rc-channel">
                              <span className="rc-channel-name">
                                RC{rc.channel} ({rc.name})
                              </span>
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

          {/* Right Column: Actions + Stream Rates */}
          <div className="params-column">
            {/* Actions Card */}
            <div className="card params-actions-card">
              <div className="actions-buttons">
                <button
                  onClick={applyRecommendedConfig}
                  disabled={!isConnected || savingParams || loadingParams || !paramsLoaded}
                  className="btn-primary"
                >
                  🚀 {t('views.flightController.applyRecommended')}
                </button>
                {validModifiedCount > 0 && (
                  <button
                    onClick={saveModifiedParams}
                    disabled={savingParams}
                    className="btn-success"
                  >
                    {savingParams ? '⏳' : '💾'} {t('views.flightController.saveChanges')} (
                    {validModifiedCount})
                  </button>
                )}
              </div>
            </div>

            {/* Stream Rates Card */}
            <div className="card">
              <h3>📡 {t('views.flightController.streamRates')}</h3>
              <p className="stream-rates-help">{t('views.flightController.streamRatesDesc')}</p>

              <div className="stream-rates-list">
                {STREAM_RATE_PARAMS.main.map((sr) => {
                  const value = getParamValue(sr.name)
                  const isMatch = isRecommendedValue(sr.name, sr.recommended)
                  const isModified = Object.hasOwn(paramsModified, sr.name)

                  return (
                    <div
                      key={sr.name}
                      className={`stream-rate-item color-${sr.color} ${
                        isModified ? 'modified' : ''
                      }`}
                    >
                      <div className="stream-rate-info">
                        <div className="stream-rate-label">
                          {sr.labelKey ? t(`views.flightController.${sr.labelKey}`) : sr.label}
                        </div>
                        <small>
                          {sr.descriptionKey
                            ? t(`views.flightController.${sr.descriptionKey}`)
                            : sr.description}
                        </small>
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
                            title={
                              isMatch
                                ? t('views.flightController.tooltipMatchesRecommended')
                                : t('views.flightController.tooltipDiffersFromRecommended', {
                                    recommended: sr.recommended,
                                  })
                            }
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
                <summary
                  onClick={(e) => {
                    e.preventDefault()
                    setShowAdvancedStreamRates(!showAdvancedStreamRates)
                  }}
                >
                  {t('views.flightController.advancedParams')}
                </summary>
                <div className="advanced-stream-content">
                  {STREAM_RATE_PARAMS.advanced.map((sr) => {
                    const value = getParamValue(sr.name)
                    return (
                      <div key={sr.name} className="stream-rate-item advanced">
                        <div className="stream-rate-info">
                          <div className="stream-rate-label">
                            {sr.labelKey ? t(`views.flightController.${sr.labelKey}`) : sr.label}
                          </div>
                          <small>
                            {sr.descriptionKey
                              ? t(`views.flightController.${sr.descriptionKey}`)
                              : sr.description}
                          </small>
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
                💡 <strong>{t('views.flightController.recommended4G')}:</strong>{' '}
                {t('views.flightController.recommended4GValues')}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default FlightControllerView
