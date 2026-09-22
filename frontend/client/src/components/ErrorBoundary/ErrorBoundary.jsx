import { Component } from 'react'
import './ErrorBoundary.css'

/**
 * Global error boundary. Renders a recoverable fallback instead of a blank
 * screen when a child throws during render/lifecycle.
 */
class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, info) {
    // Keep the console trace for debugging; no external reporting.
    console.error('UI error boundary caught an error:', error, info)
  }

  handleReload = () => {
    window.location.reload()
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary" role="alert">
          <h2>Algo ha ido mal · Something went wrong</h2>
          <p className="error-boundary-message">{String(this.state.error || 'Unknown error')}</p>
          <button type="button" className="error-boundary-reload" onClick={this.handleReload}>
            Recargar · Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

export default ErrorBoundary
