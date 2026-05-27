import './ArmedBanner.css'
import { useArmedState } from '../../hooks/useArmedState'

const ArmedBanner = () => {
  const isArmed = useArmedState()

  if (!isArmed) return null

  return (
    <div className="armed-banner" role="alert">
      <span className="armed-banner__icon">🔒</span>
      <span className="armed-banner__text">
        Drone armado — algunos controles están deshabilitados durante el vuelo
      </span>
    </div>
  )
}

export default ArmedBanner
