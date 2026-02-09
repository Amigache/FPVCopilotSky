/**
 * Modem View Constants
 * Centralized configuration for modem-related components
 */

// API Timeouts in milliseconds
export const MODEM_API_TIMEOUTS = {
  STATUS_ENHANCED: 15000, // Enhanced modem status
  BAND_CHANGE: 20000, // LTE band configuration changes
  MODE_CHANGE: 20000, // Network mode changes
  VIDEO_MODE_TOGGLE: 20000, // Video mode enable/disable
  REBOOT: 5000, // Modem reboot command
  STATUS_CHECK: 5000, // Quick status check during reboot
}

// Reboot polling configuration
export const REBOOT_CONFIG = {
  CHECK_INTERVAL: 10000, // Check every 10 seconds
  MAX_ATTEMPTS: 12, // 12 attempts = 2 minutes total
  TOTAL_TIMEOUT: 120000, // 2 minutes maximum wait
}

// Modem Status Constants
export const MODEM_STATUS = {
  AVAILABLE: 'available',
  UNAVAILABLE: 'unavailable',
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
}

// Network Mode Constants
export const NETWORK_MODES = {
  AUTO: '00', // Auto (4G/3G/2G)
  ONLY_2G: '01', // 2G Only
  ONLY_3G: '02', // 3G Only
  ONLY_4G: '03', // 4G Only
}

// Network Mode Display Names
export const NETWORK_MODE_NAMES = {
  [NETWORK_MODES.AUTO]: 'Auto (4G/3G/2G)',
  [NETWORK_MODES.ONLY_2G]: '2G Only',
  [NETWORK_MODES.ONLY_3G]: '3G Only',
  [NETWORK_MODES.ONLY_4G]: '4G Only',
}
