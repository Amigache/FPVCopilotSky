import { useTranslation } from 'react-i18next'
import Toggle from '../../Toggle/Toggle'

const StreamControlCard = ({
  streaming,
  actionLoading,
  applySettings,
  applyConfigAndStart,
  stopStream,
  restartStream,
  config,
  updateConfig,
  hasValidationErrors,
}) => {
  const { t } = useTranslation()

  return (
    <div className="card" data-testid="stream-control">
      <h2>{t('views.video.streamControl')}</h2>
      {!streaming ? (
        <div className="button-group">
          <button
            className="btn btn-apply"
            onClick={applySettings}
            disabled={actionLoading !== null || hasValidationErrors}
            title={hasValidationErrors ? t('views.video.validationErrorsPresent') : ''}
          >
            {actionLoading === 'apply' ? '⏳' : t('views.video.apply')}
          </button>
          <button
            className="btn btn-start"
            onClick={applyConfigAndStart}
            disabled={actionLoading !== null || hasValidationErrors}
            title={hasValidationErrors ? t('views.video.validationErrorsPresent') : ''}
          >
            {actionLoading === 'start' ? '⏳' : t('views.video.start')}
          </button>
        </div>
      ) : (
        <div className="button-group">
          <button className="btn btn-stop" onClick={stopStream} disabled={actionLoading !== null}>
            {actionLoading === 'stop' ? '⏳' : t('views.video.stop')}
          </button>
          <button
            className="btn btn-restart"
            onClick={restartStream}
            disabled={actionLoading !== null}
          >
            {actionLoading === 'restart' ? '⏳' : t('views.video.restart')}
          </button>
        </div>
      )}

      {/* Auto-start toggle */}
      <div className={`form-group auto-start-toggle ${streaming ? 'field-disabled' : ''}`}>
        <Toggle
          checked={config?.auto_start || false}
          onChange={(e) => updateConfig((prev) => ({ ...prev, auto_start: e.target.checked }))}
          disabled={streaming}
          label={t('views.video.autoStart')}
        />
      </div>
    </div>
  )
}

export default StreamControlCard
