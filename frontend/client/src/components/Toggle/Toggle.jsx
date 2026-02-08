import './Toggle.css'

/**
 * Reusable Toggle Switch component
 */
const Toggle = ({ checked, onChange, disabled = false, label = '', className = '' }) => {
  return (
    <label className={`toggle-label ${className}`}>
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        disabled={disabled}
        className="toggle-input"
      />
      <span className="toggle-switch"></span>
      {label && <span className="toggle-text">{label}</span>}
    </label>
  )
}

export default Toggle
