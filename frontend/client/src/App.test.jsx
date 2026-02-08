/**
 * App Component Tests
 * 
 * Tests for the main App component
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'

// Mock the useTranslation hook
vi.mock('./contexts/WebSocketContext', () => ({
  WebSocketProvider: ({ children }) => <div>{children}</div>,
  useWebSocket: () => ({
    messages: {},
    send: vi.fn(),
  }),
}))

vi.mock('./contexts/ToastContext', () => ({
  ToastProvider: ({ children }) => <div>{children}</div>,
  useToast: () => ({
    showToast: vi.fn(),
  }),
}))

vi.mock('./contexts/ModalContext', () => ({
  ModalProvider: ({ children }) => <div>{children}</div>,
  useModal: () => ({
    openModal: vi.fn(),
    closeModal: vi.fn(),
  }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => {
      // Simple translation fallback
      const translations = {
        'tabs.dashboard': 'Dashboard',
        'tabs.telemetry': 'Telemetry',
        'tabs.video': 'Video',
        'tabs.network': 'Network',
        'tabs.modem': 'Modem',
        'tabs.vpn': 'VPN',
        'tabs.flightController': 'Flight Controller',
        'tabs.system': 'System',
        'tabs.status': 'Status',
      }
      return translations[key] || key
    },
  }),
}))

// Mock components to avoid deep dependency issues
vi.mock('./components/Header/Header', () => ({
  default: () => <div data-testid="header">Header</div>,
}))

vi.mock('./components/TabBar/TabBar', () => ({
  default: ({ tabs, activeTab, onTabChange }) => (
    <div data-testid="tabbar">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          data-testid={`tab-${tab.id}`}
          onClick={() => onTabChange(tab.id)}
          className={activeTab === tab.id ? 'active' : ''}
        >
          {tab.label}
        </button>
      ))}
    </div>
  ),
}))

vi.mock('./components/Content/Content', () => ({
  default: ({ activeTab }) => <div data-testid="content">Content: {activeTab}</div>,
}))

describe('App Component', () => {
  it('renders without crashing', () => {
    render(<App />)
    expect(screen.getByTestId('header')).toBeInTheDocument()
    expect(screen.getByTestId('tabbar')).toBeInTheDocument()
    expect(screen.getByTestId('content')).toBeInTheDocument()
  })

  it('renders with correct initial tab', () => {
    render(<App />)
    expect(screen.getByText('Content: dashboard')).toBeInTheDocument()
  })

  it('changes tab on tab click', async () => {
    const user = userEvent.setup()
    render(<App />)

    const videoTab = screen.getByTestId('tab-video')
    await user.click(videoTab)

    expect(screen.getByText('Content: video')).toBeInTheDocument()
  })

  it('renders all tab buttons', () => {
    render(<App />)

    expect(screen.getByTestId('tab-dashboard')).toBeInTheDocument()
    expect(screen.getByTestId('tab-telemetry')).toBeInTheDocument()
    expect(screen.getByTestId('tab-video')).toBeInTheDocument()
    expect(screen.getByTestId('tab-network')).toBeInTheDocument()
    expect(screen.getByTestId('tab-modem')).toBeInTheDocument()
    expect(screen.getByTestId('tab-vpn')).toBeInTheDocument()
    expect(screen.getByTestId('tab-flightController')).toBeInTheDocument()
    expect(screen.getByTestId('tab-system')).toBeInTheDocument()
    expect(screen.getByTestId('tab-status')).toBeInTheDocument()
  })

  it('navigates between multiple tabs', async () => {
    const user = userEvent.setup()
    render(<App />)

    // Start at dashboard
    expect(screen.getByText('Content: dashboard')).toBeInTheDocument()

    // Click telemetry
    await user.click(screen.getByTestId('tab-telemetry'))
    expect(screen.getByText('Content: telemetry')).toBeInTheDocument()

    // Click system
    await user.click(screen.getByTestId('tab-system'))
    expect(screen.getByText('Content: system')).toBeInTheDocument()

    // Back to dashboard
    await user.click(screen.getByTestId('tab-dashboard'))
    expect(screen.getByText('Content: dashboard')).toBeInTheDocument()
  })

  it('has correct CSS classes applied', () => {
    const { container } = render(<App />)
    const appDiv = container.querySelector('.app')
    expect(appDiv).toBeInTheDocument()
  })

  it('maintains dashboard as initial active tab', () => {
    render(<App />)
    const dashboardTab = screen.getByTestId('tab-dashboard')
    expect(dashboardTab).toHaveClass('active')
  })
})
