import './App.css'
import './components/Modal.css'
import Header from './components/Header/Header'
import TabBar from './components/TabBar/TabBar'
import Content from './components/Content/Content'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { WebSocketProvider } from './contexts/WebSocketContext'
import { ToastProvider } from './contexts/ToastContext'
import { ModalProvider } from './contexts/ModalContext'

function App() {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState('dashboard')

  const tabs = [
    { id: 'dashboard', label: t('tabs.dashboard') },
    { id: 'telemetry', label: t('tabs.telemetry') },
    { id: 'video', label: t('tabs.video') },
    { id: 'network', label: t('tabs.network') },
    { id: 'modem', label: t('tabs.modem') },
    { id: 'vpn', label: t('tabs.vpn') },
    { id: 'flightController', label: t('tabs.flightController') },
    { id: 'system', label: t('tabs.system') },
    { id: 'status', label: t('tabs.status') },
  ]

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
