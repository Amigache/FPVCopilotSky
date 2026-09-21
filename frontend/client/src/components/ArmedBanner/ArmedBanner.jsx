import './ArmedBanner.css'
import { useTranslation } from 'react-i18next'
import { useArmedState } from '../../hooks/useArmedState'

const ArmedBanner = () => {
  const { t } = useTranslation()
  const isArmed = useArmedState()

  if (!isArmed) return null

  return (
    <div className="armed-banner" role="alert">
      <span className="armed-banner__icon">🔒</span>
      <span className="armed-banner__text">{t('armedBanner.message')}</span>
    </div>
  )
}

export default ArmedBanner
