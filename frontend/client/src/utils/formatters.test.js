/* eslint-env jest */
/**
 * Tests for formatting utilities
 */

import { formatBitrate } from './formatters'

describe('formatBitrate', () => {
  it('formats null/undefined as dash', () => {
    expect(formatBitrate(null)).toBe('—')
    expect(formatBitrate(undefined)).toBe('—')
  })

  it('formats zero as kbps', () => {
    expect(formatBitrate(0)).toBe('0 kbps')
  })

  it('formats values < 1000 as kbps', () => {
    expect(formatBitrate(500)).toBe('500 kbps')
    expect(formatBitrate(800)).toBe('800 kbps')
    expect(formatBitrate(999)).toBe('999 kbps')
  })

  it('formats 1000 as 1 Mbps', () => {
    expect(formatBitrate(1000)).toBe('1 Mbps')
  })

  it('formats values >= 1000 as Mbps with decimals when needed', () => {
    expect(formatBitrate(1500)).toBe('1.5 Mbps')
    expect(formatBitrate(2000)).toBe('2 Mbps')
    expect(formatBitrate(2500)).toBe('2.5 Mbps')
    expect(formatBitrate(5000)).toBe('5 Mbps')
    expect(formatBitrate(8000)).toBe('8 Mbps')
  })

  it('formats large values correctly', () => {
    expect(formatBitrate(10000)).toBe('10 Mbps')
    expect(formatBitrate(12500)).toBe('12.5 Mbps')
  })

  it('rounds to one decimal place', () => {
    expect(formatBitrate(1234)).toBe('1.2 Mbps')
    expect(formatBitrate(5678)).toBe('5.7 Mbps')
  })
})
