import './ArmedGuard.css'

/**
 * ArmedGuard — wraps any content and renders a semi-transparent
 * overlay with a lock icon when `isArmed` is true, preventing all
 * interaction with the underlying controls.
 *
 * Usage:
 *   <ArmedGuard isArmed={isArmed} message="No disponible en vuelo">
 *     <YourComponent />
 *   </ArmedGuard>
 */
const ArmedGuard = ({ children, isArmed, message }) => (
  <div className={`armed-guard${isArmed ? ' armed-guard--locked' : ''}`}>
    {children}
    {isArmed && (
      <div className="armed-guard__overlay" title="Drone armado — funcionalidad bloqueada">
        <span className="armed-guard__icon">🔒</span>
        <span className="armed-guard__message">{message || 'No disponible en vuelo'}</span>
      </div>
    )}
  </div>
)

export default ArmedGuard
