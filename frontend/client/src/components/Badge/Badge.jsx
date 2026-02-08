import './Badge.css'

const Badge = ({ variant = 'success', children }) => {
  return <span className={`badge badge-${variant}`}>{children}</span>
}

export default Badge
