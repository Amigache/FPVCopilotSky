/** Default video configuration values — single source of truth */
export const VIDEO_DEFAULTS = {
  DEVICE: '/dev/video0',
  CODEC: 'mjpeg',
  WIDTH: 960,
  HEIGHT: 720,
  FRAMERATE: 30,
  QUALITY: 85,
  H264_BITRATE: 2000,
  GOP_SIZE: 2,
  MODE: 'udp',
  UDP_HOST: '192.168.1.136',
  UDP_PORT: 5600,
  MULTICAST_GROUP: '239.1.1.1',
  MULTICAST_PORT: 5600,
  MULTICAST_TTL: 1,
  RTSP_URL: 'rtsp://localhost:8554/fpv',
  RTSP_TRANSPORT: 'tcp',
}

/** Bitrate options for H.264 encoding (kbps) */
export const BITRATE_OPTIONS = [
  { value: 500, labelKey: 'bitrateMobile' },
  { value: 1000, labelKey: null },
  { value: 2000, labelKey: 'bitrateRecommended' },
  { value: 3000, labelKey: null },
  { value: 5000, labelKey: 'bitrateWifi' },
  { value: 8000, labelKey: 'bitrateLan' },
]

/** GOP size options for keyframe interval */
export const GOP_OPTIONS = [
  { value: 1, labelKey: 'gopLowLatency' },
  { value: 2, labelKey: 'gopBalanceFpv' },
  { value: 3, labelKey: 'gopNormal' },
  { value: 5, labelKey: 'gopMoreCompression' },
  { value: 10, labelKey: 'gopHighCompression' },
  { value: 15, labelKey: 'gopMaxCompression' },
]

/** Input validation ranges */
export const RANGES = {
  QUALITY: { MIN: 10, MAX: 100 },
  PORT: { MIN: 1024, MAX: 65535 },
  TTL: { MIN: 1, MAX: 255 },
}

/** UI timing constants in milliseconds */
export const TIMING = {
  DEBOUNCE_LIVE_UPDATE: 300,
  COPY_SUCCESS_DURATION: 2000,
}

/** Fallback FPS list when camera doesn't provide frame rates */
export const FALLBACK_FPS = [30, 24, 15]

/** Default empty status shape from WebSocket */
export const EMPTY_STATUS = {
  available: false,
  streaming: false,
  enabled: true,
  config: {},
  stats: {},
  last_error: null,
  pipeline_string: '',
}

/**
 * Safe parseInt with fallback — never returns NaN.
 * @param {*} value - value to parse
 * @param {number} fallback - returned when value is not a valid integer
 * @returns {number}
 */
export const safeInt = (value, fallback = 0) => {
  const parsed = parseInt(value, 10)
  return Number.isNaN(parsed) ? fallback : parsed
}

/**
 * Validate an IPv4 multicast group address (224.0.0.0 – 239.255.255.255).
 * @param {string} ip
 * @returns {boolean}
 */
export const isValidMulticastIp = (ip) => {
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(ip)
  if (!m) return false
  const octets = m.slice(1).map(Number)
  if (octets.some((o) => o > 255)) return false
  return octets[0] >= 224 && octets[0] <= 239
}

/**
 * Validate a basic IPv4 address.
 * @param {string} ip
 * @returns {boolean}
 */
export const isValidIpv4 = (ip) => {
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(ip)
  if (!m) return false
  return m.slice(1).every((o) => Number(o) <= 255)
}

/**
 * Validate a domain name (RFC 1034/1035 compliant).
 * Allows alphanumeric, hyphens, dots. No leading/trailing hyphen in labels.
 * @param {string} domain
 * @returns {boolean}
 */
export const isValidDomain = (domain) => {
  if (!domain || domain.length > 253) return false
  // Allow localhost
  if (domain === 'localhost') return true
  // Domain regex: labels separated by dots, each label 1-63 chars
  const domainRegex =
    /^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$/
  return domainRegex.test(domain)
}

/**
 * Validate a host (either IPv4 or domain name).
 * @param {string} host
 * @returns {boolean}
 */
export const isValidHost = (host) => {
  if (!host || host.trim() === '') return false
  // If it looks like an IP (4 octets separated by dots), validate as IP only
  if (/^\d+\.\d+\.\d+\.\d+$/.test(host)) {
    return isValidIpv4(host)
  }
  // Otherwise validate as domain
  return isValidDomain(host)
}

/**
 * Validate a port number (1024-65535 for unprivileged).
 * @param {number|string} port
 * @returns {{ valid: boolean, error?: string }}
 */
export const validatePort = (port) => {
  const num = typeof port === 'string' ? parseInt(port, 10) : port
  if (Number.isNaN(num)) {
    return { valid: false, error: 'views.video.validation.invalidPort' }
  }
  if (num < RANGES.PORT.MIN || num > RANGES.PORT.MAX) {
    return { valid: false, error: 'views.video.validation.portOutOfRange' }
  }
  return { valid: true }
}

/**
 * Validate RTSP URL format.
 * @param {string} url
 * @returns {{ valid: boolean, error?: string }}
 */
export const validateRtspUrl = (url) => {
  if (!url || url.trim() === '') {
    return { valid: false, error: 'views.video.validation.emptyUrl' }
  }
  if (!url.toLowerCase().startsWith('rtsp://')) {
    return { valid: false, error: 'views.video.validation.mustStartWithRtsp' }
  }
  // Basic RTSP URL: rtsp://[user:pass@]host[:port]/path
  const rtspRegex = /^rtsp:\/\/([^@\/]+@)?([^:\/]+)(:\d+)?(\/.*)?$/i
  if (!rtspRegex.test(url)) {
    return { valid: false, error: 'views.video.validation.invalidRtspFormat' }
  }
  return { valid: true }
}
