import { memo, useState, useCallback, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../../../contexts/ToastContext'
import { PeerSelector } from '../../PeerSelector/PeerSelector'
import { fetchWithTimeout } from '../../../services/api'
import {
  OUTPUT_TYPES,
  DEFAULT_PRESETS,
  FORM_DEFAULTS,
  API_ENDPOINTS,
  validateFormData,
} from './telemetryConstants'

/**
 * OutputForm - Form component for creating/editing telemetry outputs with validation
 */
const OutputForm = memo(
  ({
    reload,
    presets = DEFAULT_PRESETS,
    editId = null,
    editData = null,
    onEditComplete = null, // Callback to exit edit mode
  }) => {
    const { t } = useTranslation()
    const { showToast } = useToast()

    // Form state
    const [formData, setFormData] = useState(() => ({
      type: editData?.type || FORM_DEFAULTS.TYPE,
      host: editData?.host || FORM_DEFAULTS.HOST,
      port: editData?.port || FORM_DEFAULTS.PORT,
    }))

    const [errors, setErrors] = useState({})
    const [loading, setLoading] = useState(false)

    // Update form data when edit data changes
    useEffect(() => {
      if (editId && editData) {
        setFormData({
          type: editData.type || FORM_DEFAULTS.TYPE,
          host: editData.host || FORM_DEFAULTS.HOST,
          port: editData.port || FORM_DEFAULTS.PORT,
        })
        setErrors({}) // Clear any existing errors
      } else {
        // Reset to defaults when not editing - use correct property mapping
        setFormData({
          type: FORM_DEFAULTS.TYPE,
          host: FORM_DEFAULTS.HOST,
          port: FORM_DEFAULTS.PORT,
        })
        setErrors({})
      }
    }, [editId, editData])

    // Handle field changes with validation
    const handleFieldChange = useCallback(
      (field, value) => {
        setFormData((prev) => ({ ...prev, [field]: value }))

        // Clear error for this field when user starts typing
        if (errors[field]) {
          setErrors((prev) => ({ ...prev, [field]: null }))
        }
      },
      [errors]
    )

    // Apply preset
    const applyPreset = useCallback(
      (presetKey) => {
        const preset = presets[presetKey]
        if (preset) {
          setFormData({
            type: preset.type,
            host: preset.host,
            port: preset.port,
          })
          setErrors({})
        }
      },
      [presets]
    )

    // Submit form
    const handleSubmit = useCallback(
      async (e) => {
        e.preventDefault()

        // Validate form data
        const validation = validateFormData(formData)
        if (!validation.isValid) {
          setErrors(validation.errors)
          showToast(t('router.validationFailed'), 'error')
          return
        }

        setLoading(true)
        setErrors({})

        try {
          const endpoint = editId ? `${API_ENDPOINTS.OUTPUTS}/${editId}` : API_ENDPOINTS.OUTPUTS

          const method = editId ? 'PUT' : 'POST'

          const response = await fetchWithTimeout(endpoint, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              type: formData.type,
              host: formData.host,
              port: parseInt(formData.port, 10),
            }),
          })

          const data = await response.json()

          if (!response.ok) {
            throw new Error(data.error || data.message || 'Operation failed')
          }

          showToast(editId ? t('router.outputUpdated') : t('router.outputCreated'), 'success')

          // Reset form and exit edit mode after successful operation
          setFormData({
            type: FORM_DEFAULTS.TYPE,
            host: FORM_DEFAULTS.HOST,
            port: FORM_DEFAULTS.PORT,
          })
          setErrors({})

          // Exit edit mode if we were editing
          if (editId && onEditComplete) {
            onEditComplete()
          }

          reload()
        } catch (error) {
          console.error('Form submission error:', error)
          showToast(error.message || t('router.operationFailed'), 'error')
        } finally {
          setLoading(false)
        }
      },
      [formData, editId, t, showToast, reload, onEditComplete]
    )

    return (
      <form onSubmit={handleSubmit} className="router-form">
        <div className="connection-grid">
          <div className="form-group">
            <label htmlFor="output-type">{t('router.type')}</label>
            <select
              id="output-type"
              value={formData.type}
              onChange={(e) => handleFieldChange('type', e.target.value)}
              disabled={loading}
              className={errors.type ? 'input-error' : ''}
            >
              <option value={OUTPUT_TYPES.TCP_SERVER}>{t('router.tcpServer')}</option>
              <option value={OUTPUT_TYPES.TCP_CLIENT}>{t('router.tcpClient')}</option>
              <option value={OUTPUT_TYPES.UDP}>{t('router.udp')}</option>
            </select>
            {errors.type && <span className="field-error">{t(errors.type)}</span>}
          </div>

          <div className="form-group">
            <label htmlFor="output-host">{t('router.host')}</label>
            <PeerSelector
              id="output-host"
              value={formData.host}
              onChange={(value) => handleFieldChange('host', value)}
              disabled={loading}
              placeholder={FORM_DEFAULTS.HOST}
              hasError={!!errors.host}
            />
            {errors.host && <span className="field-error">{t(errors.host)}</span>}
          </div>

          <div className="form-group">
            <label htmlFor="output-port">{t('router.port')}</label>
            <input
              id="output-port"
              type="number"
              value={formData.port}
              onChange={(e) => handleFieldChange('port', e.target.value)}
              disabled={loading}
              placeholder={FORM_DEFAULTS.PORT.toString()}
              className={errors.port ? 'input-error' : ''}
            />
            {errors.port && <span className="field-error">{t(errors.port)}</span>}
          </div>
        </div>

        <div className="button-group">
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? '⏳' : editId ? '💾' : '➕'}{' '}
            {editId ? t('router.update') : t('router.create')}
          </button>

          <button
            type="button"
            className="btn-secondary"
            onClick={() => applyPreset('qgc')}
            disabled={loading}
            title="QGroundControl UDP Broadcast (255.255.255.255:14550) - Permite múltiples receptores simultáneos"
          >
            📱 {t('router.presetQGC')}
          </button>

          <button
            type="button"
            className="btn-secondary"
            onClick={() => applyPreset('missionplanner')}
            disabled={loading}
            title="Mission Planner TCP Server (127.0.0.1:5760) - Servidor TCP local"
          >
            🚁 {t('router.presetMP')}
          </button>

          <button
            type="button"
            className="btn-secondary"
            onClick={() => applyPreset('udp_local')}
            disabled={loading}
            title="UDP Local (127.0.0.1:14551) - Conexión UDP local"
          >
            📡 {t('router.presetUDPLocal')}
          </button>

          <button
            type="button"
            className="btn-secondary"
            onClick={() => applyPreset('tcp_listen')}
            disabled={loading}
            title="TCP Server Listen (0.0.0.0:5761) - Escucha en todas las interfaces"
          >
            🌐 {t('router.presetTCPListen')}
          </button>
        </div>
      </form>
    )
  }
)

OutputForm.displayName = 'OutputForm'

export default OutputForm
