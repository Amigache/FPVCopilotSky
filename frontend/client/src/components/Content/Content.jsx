import { lazy, Suspense } from 'react'
import './Content.css'

// Views are code-split: each tab is loaded on demand so the initial bundle
// does not ship every page (Leaflet map, WebRTC, OpenCV, …).
const DashboardView = lazy(() => import('../Pages/DashboardView'))
const TelemetryView = lazy(() => import('../Pages/TelemetryView'))
const VideoView = lazy(() => import('../Pages/VideoView'))
const NetworkView = lazy(() => import('../Pages/NetworkView'))
const ModemView = lazy(() => import('../Pages/ModemView'))
const VPNView = lazy(() => import('../Pages/VPNView'))
const FlightControllerView = lazy(() => import('../Pages/FlightControllerView'))
const SystemView = lazy(() => import('../Pages/SystemView'))
const StatusView = lazy(() => import('../Pages/StatusView'))
const PreferencesView = lazy(() => import('../Pages/PreferencesView'))
const ExperimentalView = lazy(() => import('../Pages/ExperimentalView'))

const VIEWS = {
  dashboard: DashboardView,
  telemetry: TelemetryView,
  video: VideoView,
  network: NetworkView,
  modem: ModemView,
  vpn: VPNView,
  flightController: FlightControllerView,
  system: SystemView,
  status: StatusView,
  preferences: PreferencesView,
  experimental: ExperimentalView,
}

const Content = ({ activeTab }) => {
  const View = VIEWS[activeTab]

  return (
    <div className="content">
      <Suspense fallback={<div className="content-loading" />}>{View ? <View /> : null}</Suspense>
    </div>
  )
}

export default Content
