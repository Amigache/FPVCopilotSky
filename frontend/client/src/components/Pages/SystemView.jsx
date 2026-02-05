import './SystemView.css'
import { useTranslation } from 'react-i18next'

const SystemView = () => {
  const { t } = useTranslation()
  return (
    <div className="card">
      <h2>{t('views.system.title')}</h2>
      <div className="waiting-data">{t('views.system.waiting')}</div>
    </div>
  )
}

export default SystemView
