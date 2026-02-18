import './Content.css'
import FlightControllerView from '../Pages/FlightControllerView'
import DashboardView from '../Pages/DashboardView'
import TelemetryView from '../Pages/TelemetryView'
import VideoView from '../Pages/VideoView'
import NetworkView from '../Pages/NetworkView'
import ModemView from '../Pages/ModemView'
import VPNView from '../Pages/VPNView'
import SystemView from '../Pages/SystemView'
import StatusView from '../Pages/StatusView'
import ExperimentalView from '../Pages/ExperimentalView'
import PreferencesView from '../Pages/PreferencesView'

const Content = ({ activeTab }) => {
  return (
    <div className="content">
      {activeTab === 'dashboard' && <DashboardView />}
      {activeTab === 'telemetry' && <TelemetryView />}
      {activeTab === 'video' && <VideoView />}
      {activeTab === 'network' && <NetworkView />}
      {activeTab === 'modem' && <ModemView />}
      {activeTab === 'vpn' && <VPNView />}
      {activeTab === 'flightController' && <FlightControllerView />}
      {activeTab === 'system' && <SystemView />}
      {activeTab === 'status' && <StatusView />}
      {activeTab === 'preferences' && <PreferencesView />}
      {activeTab === 'experimental' && <ExperimentalView />}
    </div>
  )
}

export default Content
