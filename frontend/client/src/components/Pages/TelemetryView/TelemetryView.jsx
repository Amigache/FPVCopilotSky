import './TelemetryView.css'
import { useTranslation } from 'react-i18next'
import { useState, useEffect, useCallback } from 'react'
import { useToast } from '../../../contexts/ToastContext'
import { useWebSocket } from '../../../contexts/WebSocketContext'
import { fetchWithTimeout } from '../../../services/api'
import OutputForm from './OutputForm'
import OutputItem from './OutputItem'
import { API_ENDPOINTS, WEBSOCKET_EVENTS, DEFAULT_PRESETS } from './telemetryConstants'

const TelemetryView = () => {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { messages } = useWebSocket()

  // State
  const [outputs, setOutputs] = useState([])
  const [presets, setPresets] = useState(DEFAULT_PRESETS)
  const [editOutput, setEditOutput] = useState(null)

  // Load outputs
  const fetchOutputs = useCallback(async () => {
    try {
      const response = await fetchWithTimeout(API_ENDPOINTS.OUTPUTS, {
        timeout: 10000,
      })

      if (response.ok) {
        const data = await response.json()
        setOutputs(Array.isArray(data) ? data : [])
      } else {
        console.error('Failed to fetch outputs:', response.status)
        showToast(t('router.fetchError'), 'error')
      }
    } catch (error) {
      console.error('Error fetching outputs:', error)
      showToast(t('router.fetchError'), 'error')
    }
  }, [showToast, t])

  // Load presets from API
  const loadPresets = useCallback(async () => {
    try {
      const response = await fetchWithTimeout(API_ENDPOINTS.PRESETS, {
        timeout: 10000,
      })

      if (response.ok) {
        const data = await response.json()
        if (data.success && data.presets) {
          setPresets({ ...DEFAULT_PRESETS, ...data.presets })
        }
      }
    } catch (error) {
      console.error('Error loading presets:', error)
      // Keep default presets on error
    }
  }, [])

  // Load data on mount
  useEffect(() => {
    fetchOutputs()
    loadPresets()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Listen for WebSocket updates (debounced to prevent conflicts)
  useEffect(() => {
    let timeoutId
    if (messages[WEBSOCKET_EVENTS.ROUTER_STATUS]) {
      // Debounce WebSocket updates to prevent conflicts during user operations
      timeoutId = setTimeout(() => {
        const routerData = messages[WEBSOCKET_EVENTS.ROUTER_STATUS]
        if (Array.isArray(routerData)) {
          setOutputs(routerData)
        }
      }, 200) // 200ms debounce
    }
    return () => clearTimeout(timeoutId)
  }, [messages])

  // Handle edit mode
  const handleEdit = useCallback((outputId, outputData) => {
    setEditOutput({ id: outputId, data: outputData })
  }, [])

  const handleCancelEdit = useCallback(() => {
    setEditOutput(null)
  }, [])

  return (
    <div className="telemetry-container">
      <div className="card router-card">
        <h2>📡 {t('router.title')}</h2>
        <p className="card-description">{t('router.description')}</p>

        {/* Output Form */}
        <OutputForm
          reload={fetchOutputs}
          presets={presets}
          editId={editOutput?.id || null}
          editData={editOutput?.data || null}
          onEditComplete={handleCancelEdit}
        />

        {/* Cancel Edit Button */}
        {editOutput && (
          <div className="edit-controls">
            <button className="btn-secondary" onClick={handleCancelEdit}>
              ❌ {t('router.cancelEdit')}
            </button>
          </div>
        )}

        {/* Configured Outputs */}
        {outputs.length > 0 && (
          <div className="outputs-section">
            <h3>📋 {t('router.configuredOutputs')}</h3>
            <div className="outputs-list">
              {outputs.map((output) => (
                <OutputItem
                  key={output.id}
                  output={output}
                  reload={fetchOutputs}
                  onEdit={handleEdit}
                  isEditing={editOutput?.id === output.id}
                  onCancelEdit={handleCancelEdit}
                />
              ))}
            </div>
          </div>
        )}

        {outputs.length === 0 && (
          <div className="empty-state">
            <p>{t('router.noOutputs')}</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default TelemetryView
