/**
 * videoConstants — unit tests for helpers and constants
 *
 * Tests safeInt, isValidMulticastIp, isValidIpv4 and constant shapes.
 */

import { describe, it, expect } from 'vitest'
import {
  safeInt,
  isValidMulticastIp,
  isValidIpv4,
  isValidDomain,
  isValidHost,
  validatePort,
  validateRtspUrl,
  VIDEO_DEFAULTS,
  BITRATE_OPTIONS,
  GOP_OPTIONS,
  RANGES,
  TIMING,
  FALLBACK_FPS,
  EMPTY_STATUS,
} from './videoConstants'

// ---------------------------------------------------------------------------
// safeInt
// ---------------------------------------------------------------------------
describe('safeInt', () => {
  it('parses valid integers', () => {
    expect(safeInt('42', 0)).toBe(42)
    expect(safeInt(100, 0)).toBe(100)
    expect(safeInt('0', 5)).toBe(0)
    expect(safeInt('-1', 5)).toBe(-1)
  })

  it('returns fallback for NaN-producing inputs', () => {
    expect(safeInt('abc', 7)).toBe(7)
    expect(safeInt(undefined, 10)).toBe(10)
    expect(safeInt(null, 3)).toBe(3)
    expect(safeInt('', 99)).toBe(99)
    expect(safeInt(NaN, 42)).toBe(42)
  })

  it('defaults fallback to 0 when omitted', () => {
    expect(safeInt('not-a-number')).toBe(0)
  })

  it('truncates decimals like parseInt', () => {
    expect(safeInt('3.9', 0)).toBe(3)
    expect(safeInt(9.7, 0)).toBe(9)
  })
})

// ---------------------------------------------------------------------------
// isValidMulticastIp
// ---------------------------------------------------------------------------
describe('isValidMulticastIp', () => {
  it('accepts valid multicast addresses', () => {
    expect(isValidMulticastIp('224.0.0.1')).toBe(true)
    expect(isValidMulticastIp('239.255.255.255')).toBe(true)
    expect(isValidMulticastIp('239.1.1.1')).toBe(true)
    expect(isValidMulticastIp('224.0.0.0')).toBe(true)
  })

  it('rejects unicast addresses', () => {
    expect(isValidMulticastIp('192.168.1.1')).toBe(false)
    expect(isValidMulticastIp('10.0.0.1')).toBe(false)
    expect(isValidMulticastIp('127.0.0.1')).toBe(false)
  })

  it('rejects above-range first octets', () => {
    expect(isValidMulticastIp('240.0.0.1')).toBe(false)
    expect(isValidMulticastIp('255.255.255.255')).toBe(false)
  })

  it('rejects invalid formats', () => {
    expect(isValidMulticastIp('not-an-ip')).toBe(false)
    expect(isValidMulticastIp('')).toBe(false)
    expect(isValidMulticastIp('300.1.1.1')).toBe(false)
    expect(isValidMulticastIp('239.1.1')).toBe(false)
    expect(isValidMulticastIp('239.1.1.1.1')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// isValidIpv4
// ---------------------------------------------------------------------------
describe('isValidIpv4', () => {
  it('accepts valid IPv4 addresses', () => {
    expect(isValidIpv4('192.168.1.100')).toBe(true)
    expect(isValidIpv4('0.0.0.0')).toBe(true)
    expect(isValidIpv4('255.255.255.255')).toBe(true)
    expect(isValidIpv4('10.0.0.1')).toBe(true)
  })

  it('rejects invalid addresses', () => {
    expect(isValidIpv4('abc')).toBe(false)
    expect(isValidIpv4('999.1.1.1')).toBe(false)
    expect(isValidIpv4('1.2.3')).toBe(false)
    expect(isValidIpv4('')).toBe(false)
    expect(isValidIpv4('1.2.3.4.5')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// Constants structure checks
// ---------------------------------------------------------------------------
describe('VIDEO_DEFAULTS', () => {
  it('has all essential keys', () => {
    const keys = [
      'DEVICE',
      'CODEC',
      'WIDTH',
      'HEIGHT',
      'FRAMERATE',
      'QUALITY',
      'H264_BITRATE',
      'GOP_SIZE',
      'MODE',
      'UDP_HOST',
      'UDP_PORT',
      'MULTICAST_GROUP',
      'MULTICAST_PORT',
      'MULTICAST_TTL',
      'RTSP_URL',
      'RTSP_TRANSPORT',
    ]
    keys.forEach((k) => expect(VIDEO_DEFAULTS).toHaveProperty(k))
  })

  it('has sensible numeric defaults', () => {
    expect(VIDEO_DEFAULTS.WIDTH).toBeGreaterThan(0)
    expect(VIDEO_DEFAULTS.HEIGHT).toBeGreaterThan(0)
    expect(VIDEO_DEFAULTS.FRAMERATE).toBeGreaterThanOrEqual(1)
    expect(VIDEO_DEFAULTS.QUALITY).toBeGreaterThanOrEqual(1)
    expect(VIDEO_DEFAULTS.QUALITY).toBeLessThanOrEqual(100)
  })
})

describe('BITRATE_OPTIONS', () => {
  it('is a non-empty array of {value, labelKey}', () => {
    expect(BITRATE_OPTIONS.length).toBeGreaterThan(0)
    BITRATE_OPTIONS.forEach((opt) => {
      expect(opt).toHaveProperty('value')
      expect(typeof opt.value).toBe('number')
    })
  })
})

describe('GOP_OPTIONS', () => {
  it('is a non-empty array of {value, labelKey}', () => {
    expect(GOP_OPTIONS.length).toBeGreaterThan(0)
    GOP_OPTIONS.forEach((opt) => {
      expect(opt).toHaveProperty('value')
      expect(typeof opt.value).toBe('number')
    })
  })
})

describe('RANGES', () => {
  it('has QUALITY with MIN < MAX', () => {
    expect(RANGES.QUALITY.MIN).toBeLessThan(RANGES.QUALITY.MAX)
  })
  it('has PORT with MIN < MAX', () => {
    expect(RANGES.PORT.MIN).toBeLessThan(RANGES.PORT.MAX)
  })
  it('has TTL with MIN < MAX', () => {
    expect(RANGES.TTL.MIN).toBeLessThan(RANGES.TTL.MAX)
  })
})

describe('TIMING', () => {
  it('has positive DEBOUNCE_LIVE_UPDATE', () => {
    expect(TIMING.DEBOUNCE_LIVE_UPDATE).toBeGreaterThan(0)
  })
})

describe('FALLBACK_FPS', () => {
  it('is a non-empty array of positive numbers', () => {
    expect(FALLBACK_FPS.length).toBeGreaterThan(0)
    FALLBACK_FPS.forEach((fps) => expect(fps).toBeGreaterThan(0))
  })
})

describe('EMPTY_STATUS', () => {
  it('has streaming: false and available: false', () => {
    expect(EMPTY_STATUS.streaming).toBe(false)
    expect(EMPTY_STATUS.available).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// isValidDomain
// ---------------------------------------------------------------------------
describe('isValidDomain', () => {
  it('accepts valid domain names', () => {
    expect(isValidDomain('example.com')).toBe(true)
    expect(isValidDomain('sub.example.com')).toBe(true)
    expect(isValidDomain('localhost')).toBe(true)
    expect(isValidDomain('my-server.local')).toBe(true)
    expect(isValidDomain('test123.example.org')).toBe(true)
  })

  it('rejects invalid domains', () => {
    expect(isValidDomain('')).toBe(false)
    expect(isValidDomain('-example.com')).toBe(false)
    expect(isValidDomain('example-.com')).toBe(false)
    expect(isValidDomain('.example.com')).toBe(false)
    expect(isValidDomain('example..com')).toBe(false)
    expect(isValidDomain('a'.repeat(254))).toBe(false) // too long
  })
})

// ---------------------------------------------------------------------------
// isValidHost
// ---------------------------------------------------------------------------
describe('isValidHost', () => {
  it('accepts valid IPv4 addresses', () => {
    expect(isValidHost('192.168.1.1')).toBe(true)
    expect(isValidHost('10.0.0.1')).toBe(true)
  })

  it('accepts valid domain names', () => {
    expect(isValidHost('example.com')).toBe(true)
    expect(isValidHost('localhost')).toBe(true)
  })

  it('rejects invalid inputs', () => {
    expect(isValidHost('')).toBe(false)
    expect(isValidHost('999.999.999.999')).toBe(false)
    expect(isValidHost('-invalid')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// validatePort
// ---------------------------------------------------------------------------
describe('validatePort', () => {
  it('accepts valid ports in range', () => {
    expect(validatePort(1024)).toEqual({ valid: true })
    expect(validatePort(5000)).toEqual({ valid: true })
    expect(validatePort(65535)).toEqual({ valid: true })
    expect(validatePort('8080')).toEqual({ valid: true })
  })

  it('rejects ports out of range', () => {
    const result1 = validatePort(1023)
    expect(result1.valid).toBe(false)
    expect(result1.error).toBe('views.video.validation.portOutOfRange')

    const result2 = validatePort(65536)
    expect(result2.valid).toBe(false)
    expect(result2.error).toBe('views.video.validation.portOutOfRange')
  })

  it('rejects invalid port values', () => {
    const result = validatePort('abc')
    expect(result.valid).toBe(false)
    expect(result.error).toBe('views.video.validation.invalidPort')
  })
})

// ---------------------------------------------------------------------------
// validateRtspUrl
// ---------------------------------------------------------------------------
describe('validateRtspUrl', () => {
  it('accepts valid RTSP URLs', () => {
    expect(validateRtspUrl('rtsp://192.168.1.1:8554/fpv')).toEqual({ valid: true })
    expect(validateRtspUrl('rtsp://example.com/stream')).toEqual({ valid: true })
    expect(validateRtspUrl('rtsp://user:pass@server.local:554/path')).toEqual({ valid: true })
  })

  it('rejects empty URLs', () => {
    const result = validateRtspUrl('')
    expect(result.valid).toBe(false)
    expect(result.error).toBe('views.video.validation.emptyUrl')
  })

  it('rejects URLs not starting with rtsp://', () => {
    const result = validateRtspUrl('http://example.com')
    expect(result.valid).toBe(false)
    expect(result.error).toBe('views.video.validation.mustStartWithRtsp')
  })

  it('rejects malformed RTSP URLs', () => {
    const result = validateRtspUrl('rtsp://')
    expect(result.valid).toBe(false)
    expect(result.error).toBe('views.video.validation.invalidRtspFormat')
  })
})
