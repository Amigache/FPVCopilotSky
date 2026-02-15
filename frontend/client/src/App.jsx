import './App.css'
import './components/Modal.css'
import Header from './components/Header/Header'
import TabBar from './components/TabBar/TabBar'
import Content from './components/Content/Content'
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { WebSocketProvider } from './contexts/WebSocketContext'
import { ToastProvider } from './contexts/ToastContext'
import { ModalProvider } from './contexts/ModalContext'
import api from './services/api'

function App() {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState('dashboard')
  const [experimentalTabEnabled, setExperimentalTabEnabled] = useState(true)

  // Load preferences to check if experimental tab is enabled
  useEffect(() => {
    const loadPreferences = async () => {
      try {
        const response = await api.get('/api/system/preferences')
        if (response.ok) {
          const data = await response.json()
          if (data.extras) {
            setExperimentalTabEnabled(data.extras.experimental_tab_enabled !== false)
          }
        }
      } catch (error) {
        console.error('Error loading preferences:', error)
      }
    }
    loadPreferences()

    // Listen for experimental tab toggle events
    const handleExperimentalToggle = (event) => {
      setExperimentalTabEnabled(event.detail.enabled)
      // If disabling and currently on experimental tab, switch to dashboard
      if (!event.detail.enabled && activeTab === 'experimental') {
        setActiveTab('dashboard')
      }
    }

    window.addEventListener('experimentalTabToggled', handleExperimentalToggle)
    return () => {
      window.removeEventListener('experimentalTabToggled', handleExperimentalToggle)
    }
  }, [activeTab])

  const allTabs = [
    { id: 'dashboard', label: t('tabs.dashboard') },
    { id: 'telemetry', label: t('tabs.telemetry') },
    { id: 'video', label: t('tabs.video') },
    { id: 'network', label: t('tabs.network') },
    { id: 'modem', label: t('tabs.modem') },
    { id: 'vpn', label: t('tabs.vpn') },
    { id: 'flightController', label: t('tabs.flightController') },
    { id: 'system', label: t('tabs.system') },
    { id: 'status', label: t('tabs.status') },
    { id: 'experimental', label: t('tabs.experimental') },
  ]

  // Filter tabs based on preferences
  const tabs = experimentalTabEnabled ? allTabs : allTabs.filter((tab) => tab.id !== 'experimental')

  return (
    <ModalProvider>
      <ToastProvider>
        <WebSocketProvider>
          <div className="app">
            <Header />
            <TabBar tabs={tabs} activeTab={activeTab} onTabChange={setActiveTab} />
            <Content activeTab={activeTab} />
          </div>
        </WebSocketProvider>
      </ToastProvider>
    </ModalProvider>
  )
}

export default App
