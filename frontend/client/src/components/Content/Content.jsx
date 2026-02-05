import './Content.css'
import FlightControllerView from '../Pages/FlightControllerView'
import DashboardView from '../Pages/DashboardView'
import TelemetryView from '../Pages/TelemetryView'
import VideoView from '../Pages/VideoView'
import NetworkView from '../Pages/NetworkView'
import VPNView from '../Pages/VPNView'
import SystemView from '../Pages/SystemView'

const Content = ({ activeTab }) => {
  return (
    <div className="content">
      {activeTab === 'dashboard' && <DashboardView />}
      {activeTab === 'telemetry' && <TelemetryView />}
      {activeTab === 'video' && <VideoView />}
      {activeTab === 'network' && <NetworkView />}
      {activeTab === 'vpn' && <VPNView />}
      {activeTab === 'flightController' && <FlightControllerView />}
      {activeTab === 'system' && <SystemView />}
    </div>
  )
}

export default Content
