import { useTranslation } from 'react-i18next'

const PipelineCard = ({ pipelineString, onCopy, copySuccess }) => {
  const { t } = useTranslation()

  return (
    <div className="card">
      <h2>{t('views.video.pipelineTitle')}</h2>
      <div className="info-box">{t('views.video.pipelineInstructions')}</div>
      <div className="pipeline-box">
        <code>{pipelineString}</code>
      </div>
      <button
        className={`btn btn-copy ${copySuccess ? 'success' : ''}`}
        onClick={() => onCopy(pipelineString)}
      >
        {copySuccess ? t('views.video.copied') : t('views.video.copyToClipboard')}
      </button>
    </div>
  )
}

export default PipelineCard
