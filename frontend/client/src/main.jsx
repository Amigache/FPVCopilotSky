import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './i18n/config'
import App from './App.jsx'
import { initScrollbarFix } from './utils/scrollbarFix'

// Initialize scrollbar fix for Chrome mobile layout shift
initScrollbarFix()

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
