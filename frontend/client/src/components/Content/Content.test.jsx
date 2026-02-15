/**
 * Content Component Tests
 *
 * Tests for the Content component that renders different views based on activeTab
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

describe('Content Component', () => {
  it('renders dashboard view when activeTab is dashboard', () => {
    render(<Content activeTab="dashboard" />)
    expect(screen.getByTestId('dashboard-view')).toBeInTheDocument()
  })

  it('renders telemetry view when activeTab is telemetry', () => {
    render(<Content activeTab="telemetry" />)
    expect(screen.getByTestId('telemetry-view')).toBeInTheDocument()
  })

  it('renders video view when activeTab is video', () => {
    render(<Content activeTab="video" />)
    expect(screen.getByTestId('video-view')).toBeInTheDocument()
  })

  it('renders network view when activeTab is network', () => {
    render(<Content activeTab="network" />)
    expect(screen.getByTestId('network-view')).toBeInTheDocument()
  })

  it('renders modem view when activeTab is modem', () => {
    render(<Content activeTab="modem" />)
    expect(screen.getByTestId('modem-view')).toBeInTheDocument()
  })

  it('renders vpn view when activeTab is vpn', () => {
    render(<Content activeTab="vpn" />)
    expect(screen.getByTestId('vpn-view')).toBeInTheDocument()
  })

  it('renders flight controller view when activeTab is flightController', () => {
    render(<Content activeTab="flightController" />)
    expect(screen.getByTestId('flight-controller-view')).toBeInTheDocument()
  })

  it('renders system view when activeTab is system', () => {
    render(<Content activeTab="system" />)
    expect(screen.getByTestId('system-view')).toBeInTheDocument()
  })

  it('renders status view when activeTab is status', () => {
    render(<Content activeTab="status" />)
    expect(screen.getByTestId('status-view')).toBeInTheDocument()
  })

  it('renders experimental view when activeTab is experimental', () => {
    render(<Content activeTab="experimental" />)
    expect(screen.getByTestId('experimental-view')).toBeInTheDocument()
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
