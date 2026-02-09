import { describe, it, expect } from 'vitest'
import {
  OUTPUT_TYPES,
  DEFAULT_PRESETS,
  VALIDATION,
  API_ENDPOINTS,
  WEBSOCKET_EVENTS,
} from '../telemetryConstants'

describe('TelemetryConstants', () => {
  describe('OUTPUT_TYPES', () => {
    it('has all required types', () => {
      expect(OUTPUT_TYPES).toHaveProperty('TCP_SERVER', 'tcp_server')
      expect(OUTPUT_TYPES).toHaveProperty('TCP_CLIENT', 'tcp_client')
      expect(OUTPUT_TYPES).toHaveProperty('UDP', 'udp')
    })

    it('has consistent naming convention', () => {
      Object.values(OUTPUT_TYPES).forEach((type) => {
        expect(type).toMatch(/^[a-z_]+$/)
      })
    })
  })

  describe('DEFAULT_PRESETS', () => {
    it('has QGC preset', () => {
      expect(DEFAULT_PRESETS.qgc).toBeDefined()
      expect(DEFAULT_PRESETS.qgc.type).toBe(OUTPUT_TYPES.UDP)
      expect(DEFAULT_PRESETS.qgc.host).toBe('255.255.255.255')
      expect(DEFAULT_PRESETS.qgc.port).toBe(14550)
    })

    it('has Mission Planner preset', () => {
      expect(DEFAULT_PRESETS.missionplanner).toBeDefined()
      expect(DEFAULT_PRESETS.missionplanner.type).toBe(OUTPUT_TYPES.TCP_CLIENT)
      expect(DEFAULT_PRESETS.missionplanner.host).toBe('127.0.0.1')
      expect(DEFAULT_PRESETS.missionplanner.port).toBe(5760)
    })

    it('has valid port numbers', () => {
      Object.values(DEFAULT_PRESETS).forEach((preset) => {
        expect(preset.port).toBeGreaterThan(1023)
        expect(preset.port).toBeLessThan(65536)
        expect(Number.isInteger(preset.port)).toBe(true)
      })
    })

    it('has valid host addresses', () => {
      Object.values(DEFAULT_PRESETS).forEach((preset) => {
        expect(preset.host).toMatch(/^[\d.]+$/)
        expect(preset.host).not.toBe('')
      })
    })
  })

  describe('VALIDATION', () => {
    it('has port validation constants', () => {
      expect(VALIDATION.PORT.MIN).toBe(1024)
      expect(VALIDATION.PORT.MAX).toBe(65535)
    })

    it('has host validation pattern', () => {
      expect(VALIDATION.HOST.PATTERN).toBeInstanceOf(RegExp)

      // Test pattern with valid addresses
      expect(VALIDATION.HOST.PATTERN.test('127.0.0.1')).toBe(true)
      expect(VALIDATION.HOST.PATTERN.test('0.0.0.0')).toBe(true)
      expect(VALIDATION.HOST.PATTERN.test('255.255.255.255')).toBe(true)

      // Test pattern with invalid addresses
      expect(VALIDATION.HOST.PATTERN.test('256.1.1.1')).toBe(false)
      expect(VALIDATION.HOST.PATTERN.test('192.168.1')).toBe(false)
      expect(VALIDATION.HOST.PATTERN.test('invalid')).toBe(false)
    })

    it('has valid port range', () => {
      expect(VALIDATION.PORT.MIN).toBeLessThan(VALIDATION.PORT.MAX)
      expect(VALIDATION.PORT.MIN).toBeGreaterThan(1023) // avoid system ports
      expect(VALIDATION.PORT.MAX).toBeLessThanOrEqual(65535) // max port number
    })
  })

  describe('API_ENDPOINTS', () => {
    it('has all required endpoints', () => {
      expect(API_ENDPOINTS.BASE).toBe('/api/mavlink-router')
      expect(API_ENDPOINTS.OUTPUTS).toBe('/api/mavlink-router/outputs')
      expect(API_ENDPOINTS.PRESETS).toBe('/api/mavlink-router/presets')
      expect(API_ENDPOINTS.RESTART).toBe('/api/mavlink-router/restart')
    })

    it('follows consistent path pattern', () => {
      Object.values(API_ENDPOINTS).forEach((endpoint) => {
        expect(endpoint).toMatch(/^\/api\/mavlink-router(\/\w+)?$/)
      })
    })
  })

  describe('WEBSOCKET_EVENTS', () => {
    it('has required events', () => {
      expect(WEBSOCKET_EVENTS.ROUTER_STATUS).toBe('router_status')
    })

    it('follows snake_case convention', () => {
      Object.values(WEBSOCKET_EVENTS).forEach((event) => {
        expect(event).toMatch(/^[a-z_]+$/)
      })
    })
  })

  describe('Integration', () => {
    it('presets use valid output types', () => {
      Object.values(DEFAULT_PRESETS).forEach((preset) => {
        expect(Object.values(OUTPUT_TYPES)).toContain(preset.type)
      })
    })

    it('presets follow validation rules', () => {
      Object.values(DEFAULT_PRESETS).forEach((preset) => {
        expect(preset.port).toBeGreaterThanOrEqual(VALIDATION.PORT.MIN)
        expect(preset.port).toBeLessThanOrEqual(VALIDATION.PORT.MAX)
        expect(VALIDATION.HOST.PATTERN.test(preset.host)).toBe(true)
      })
    })
  })
})
