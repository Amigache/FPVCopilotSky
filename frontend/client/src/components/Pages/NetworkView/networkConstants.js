/**
 * Network View Constants
 * Centralized configuration for network-related components
 */

// API Timeouts in milliseconds
export const API_TIMEOUTS = {
  DASHBOARD: 15000, // Dashboard unified endpoint
  WIFI_SCAN: 10000, // WiFi network scan
  STATUS: 8000, // General status queries
  CONNECTION: 12000, // Network connection operations
}

// UI Animation Delays in milliseconds
export const UI_DELAYS = {
  WIFI_SCAN_ANIMATION: 300, // Brief animation delay for loading spinner
  REFRESH_COOLDOWN: 1000, // Minimum time between refresh operations
}

// Network Status Constants
export const NETWORK_MODES = {
  WIFI: 'wifi',
  MODEM: 'modem',
  UNKNOWN: 'unknown',
}

// Signal Strength Thresholds
export const SIGNAL_THRESHOLDS = {
  EXCELLENT: 75,
  GOOD: 50,
  FAIR: 25,
  POOR: 0,
}

// Signal bars calculation
export const getSignalBars = (signalPercent) => {
  if (signalPercent >= SIGNAL_THRESHOLDS.EXCELLENT) return 4
  if (signalPercent >= SIGNAL_THRESHOLDS.GOOD) return 3
  if (signalPercent >= SIGNAL_THRESHOLDS.FAIR) return 2
  return 1
}

// Signal category classification
export const getSignalCategory = (signalPercent) => {
  if (signalPercent >= SIGNAL_THRESHOLDS.EXCELLENT) return 'excellent'
  if (signalPercent >= SIGNAL_THRESHOLDS.GOOD) return 'good'
  if (signalPercent >= SIGNAL_THRESHOLDS.FAIR) return 'fair'
  return 'poor'
}
