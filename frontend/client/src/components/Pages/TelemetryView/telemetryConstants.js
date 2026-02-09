/**
 * TelemetryView Constants
 * Centralized constants for telemetry/MAVLink router functionality
 */

// Output types
export const OUTPUT_TYPES = {
  TCP_SERVER: 'tcp_server',
  TCP_CLIENT: 'tcp_client',
  UDP: 'udp',
}

// Default presets
export const DEFAULT_PRESETS = {
  qgc: {
    type: OUTPUT_TYPES.UDP,
    host: '255.255.255.255', // IP broadcast - permite múltiples receptores
    port: 14550,
  },
  missionplanner: {
    type: OUTPUT_TYPES.TCP_SERVER,
    host: '127.0.0.1',
    port: 5760,
  },
  udp_local: {
    type: OUTPUT_TYPES.UDP,
    host: '127.0.0.1',
    port: 14551,
  },
  tcp_listen: {
    type: OUTPUT_TYPES.TCP_SERVER,
    host: '0.0.0.0',
    port: 5761,
  },
}

// Validation ranges following VideoView pattern
export const VALIDATION = {
  PORT: {
    MIN: 1024,
    MAX: 65535,
  },
  HOST: {
    PATTERN:
      /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/,
  },
}

// API endpoints
export const API_ENDPOINTS = {
  BASE: '/api/mavlink-router',
  OUTPUTS: '/api/mavlink-router/outputs',
  PRESETS: '/api/mavlink-router/presets',
  RESTART: '/api/mavlink-router/restart',
}

// WebSocket events
export const WEBSOCKET_EVENTS = {
  ROUTER_STATUS: 'router_status',
}

// Form defaults
export const FORM_DEFAULTS = {
  TYPE: OUTPUT_TYPES.UDP,
  HOST: '127.0.0.1',
  PORT: 14550,
}

// Status indicators
export const STATUS_INDICATORS = {
  running: '🟢',
  stopped: '🔴',
}

// Validation helper functions
export const isValidPort = (port) => {
  const numPort = parseInt(port, 10)
  return !isNaN(numPort) && numPort >= VALIDATION.PORT.MIN && numPort <= VALIDATION.PORT.MAX
}

// Acepta IPs y hostnames (DNS)
export const isValidHost = (host) => {
  if (!host || typeof host !== 'string') return false

  // IP v4 pattern
  const ipPattern =
    /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/

  // Hostname pattern (alphanumeric, dots, hyphens)
  const hostnamePattern =
    /^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$/

  return ipPattern.test(host) || hostnamePattern.test(host)
}

// Devuelve claves de traducción para i18n
export const validateFormData = (formData) => {
  const errors = {}

  if (!formData.type) {
    errors.type = 'router.validation.typeRequired'
  }

  if (!formData.host) {
    errors.host = 'router.validation.hostRequired'
  } else if (!isValidHost(formData.host)) {
    errors.host = 'router.validation.invalidHost'
  }

  if (!formData.port) {
    errors.port = 'router.validation.portRequired'
  } else if (!isValidPort(formData.port)) {
    errors.port = 'router.validation.invalidPort'
  }

  return {
    isValid: Object.keys(errors).length === 0,
    errors,
  }
}
