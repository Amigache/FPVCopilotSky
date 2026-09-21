/**
 * Content Component Tests
 *
 * Tests for the Content component that renders different views based on activeTab.
 * Views are lazy-loaded, so assertions wait for the code-split chunk.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import Content from './Content'

// Mock all view components
vi.mock('../Pages/FlightControllerView', () => ({
  default: () => <div data-testid="flight-controller-view">FlightController View</div>,
}))
vi.mock('../Pages/DashboardView', () => ({
  default: () => <div data-testid="dashboard-view">Dashboard View</div>,
}))
vi.mock('../Pages/TelemetryView', () => ({
  default: () => <div data-testid="telemetry-view">Telemetry View</div>,
}))
vi.mock('../Pages/VideoView', () => ({
  default: () => <div data-testid="video-view">Video View</div>,
}))
vi.mock('../Pages/NetworkView', () => ({
  default: () => <div data-testid="network-view">Network View</div>,
}))
vi.mock('../Pages/ModemView', () => ({
  default: () => <div data-testid="modem-view">Modem View</div>,
}))
vi.mock('../Pages/VPNView', () => ({
  default: () => <div data-testid="vpn-view">VPN View</div>,
}))
vi.mock('../Pages/SystemView', () => ({
  default: () => <div data-testid="system-view">System View</div>,
}))
vi.mock('../Pages/StatusView', () => ({
  default: () => <div data-testid="status-view">Status View</div>,
}))
vi.mock('../Pages/ExperimentalView', () => ({
  default: () => <div data-testid="experimental-view">Experimental View</div>,
}))
vi.mock('../Pages/PreferencesView', () => ({
  default: () => <div data-testid="preferences-view">Preferences View</div>,
}))

describe('Content Component', () => {
  it('renders dashboard view when activeTab is dashboard', async () => {
    render(<Content activeTab="dashboard" />)
    expect(await screen.findByTestId('dashboard-view')).toBeInTheDocument()
  })

  it('renders telemetry view when activeTab is telemetry', async () => {
    render(<Content activeTab="telemetry" />)
    expect(await screen.findByTestId('telemetry-view')).toBeInTheDocument()
  })

  it('renders video view when activeTab is video', async () => {
    render(<Content activeTab="video" />)
    expect(await screen.findByTestId('video-view')).toBeInTheDocument()
  })

  it('renders network view when activeTab is network', async () => {
    render(<Content activeTab="network" />)
    expect(await screen.findByTestId('network-view')).toBeInTheDocument()
  })

  it('renders modem view when activeTab is modem', async () => {
    render(<Content activeTab="modem" />)
    expect(await screen.findByTestId('modem-view')).toBeInTheDocument()
  })

  it('renders vpn view when activeTab is vpn', async () => {
    render(<Content activeTab="vpn" />)
    expect(await screen.findByTestId('vpn-view')).toBeInTheDocument()
  })

  it('renders flight controller view when activeTab is flightController', async () => {
    render(<Content activeTab="flightController" />)
    expect(await screen.findByTestId('flight-controller-view')).toBeInTheDocument()
  })

  it('renders system view when activeTab is system', async () => {
    render(<Content activeTab="system" />)
    expect(await screen.findByTestId('system-view')).toBeInTheDocument()
  })

  it('renders status view when activeTab is status', async () => {
    render(<Content activeTab="status" />)
    expect(await screen.findByTestId('status-view')).toBeInTheDocument()
  })

  it('renders preferences view when activeTab is preferences', async () => {
    render(<Content activeTab="preferences" />)
    expect(await screen.findByTestId('preferences-view')).toBeInTheDocument()
  })

  it('renders experimental view when activeTab is experimental', async () => {
    render(<Content activeTab="experimental" />)
    expect(await screen.findByTestId('experimental-view')).toBeInTheDocument()
  })

  it('renders nothing when activeTab is unknown', () => {
    const { container } = render(<Content activeTab="unknown" />)
    // Should only have the content wrapper div
    expect(container.querySelector('.content').children.length).toBe(0)
  })

  it('renders correct structure with content class', () => {
    render(<Content activeTab="dashboard" />)
    const contentDiv = document.querySelector('.content')
    expect(contentDiv).toBeInTheDocument()
  })
})
