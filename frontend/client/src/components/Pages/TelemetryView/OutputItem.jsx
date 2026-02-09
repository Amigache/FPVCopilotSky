import { memo, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useToast } from '../../../contexts/ToastContext'
import { useModal } from '../../../contexts/ModalContext'
import { fetchWithTimeout } from '../../../services/api'
import { API_ENDPOINTS, OUTPUT_TYPES } from './telemetryConstants'

/**
 * OutputItem - Individual output display component
 */
const OutputItem = memo(({ output, reload, onEdit, isEditing = false, onCancelEdit }) => {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { showModal } = useModal()

  // Get type label
  const getTypeLabel = (type) => {
    switch (type) {
      case OUTPUT_TYPES.TCP_SERVER:
        return t('router.tcpServer')
      case OUTPUT_TYPES.TCP_CLIENT:
        return t('router.tcpClient')
      case OUTPUT_TYPES.UDP:
        return t('router.udp')
      default:
        return type
    }
  }

  // Handle delete
  const handleDelete = useCallback(async () => {
    showModal({
      title: t('router.confirmDelete'),
      message: `${t('router.confirmDeleteMessage')} ${output.host}:${output.port}?`,
      type: 'confirm',
      confirmText: t('router.delete'),
      cancelText: t('router.cancel'),
      onConfirm: async () => {
        try {
          const response = await fetchWithTimeout(`${API_ENDPOINTS.OUTPUTS}/${output.id}`, {
            method: 'DELETE',
          })

          const data = await response.json()

          if (!response.ok) {
            throw new Error(data.error || data.message || 'Delete failed')
          }

          showToast(t('router.outputDeleted'), 'success')
          // Si esta salida estaba siendo editada, cancelar la edición
          if (isEditing && onCancelEdit) {
            onCancelEdit()
          }
          reload()
        } catch (error) {
          console.error('Delete error:', error)
          showToast(error.message || t('router.deleteError'), 'error')
        }
      },
    })
  }, [output, t, showModal, showToast, reload, isEditing, onCancelEdit])

  // Handle restart
  const handleRestart = useCallback(async () => {
    try {
      const response = await fetchWithTimeout(`${API_ENDPOINTS.OUTPUTS}/${output.id}/restart`, {
        method: 'POST',
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.error || data.message || 'Restart failed')
      }

      showToast(t('router.outputRestarted'), 'success')
      reload()
    } catch (error) {
      console.error('Restart error:', error)
      showToast(error.message || t('router.restartError'), 'error')
    }
  }, [output, t, showToast, reload])
  return (
    <div className={`output-item ${output.running ? 'active' : ''}`}>
      <div className="output-info">
        <span className={`status-indicator ${output.running ? 'running' : 'stopped'}`}>
          {output.running ? '🟢' : '🔴'}
        </span>

        <span className="output-type">{getTypeLabel(output.type)}</span>

        <span className="output-address">
          {output.host}:{output.port}
        </span>

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
          className="btn-edit"
          onClick={() =>
            onEdit(output.id, {
              type: output.type,
              host: output.host,
              port: output.port,
            })
          }
          title={t('router.edit')}
        >
          ✏️ {t('router.edit')}
        </button>

        <button className="btn-secondary" onClick={handleRestart} title={t('router.restart')}>
          🔄 {t('router.restart')}
        </button>

        <button className="btn-delete" onClick={handleDelete} title={t('router.delete')}>
          🗑 {t('router.delete')}
        </button>
      </div>
    </div>
  )
})

OutputItem.displayName = 'OutputItem'

export default OutputItem
