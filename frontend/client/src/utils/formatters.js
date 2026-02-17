/**
 * Formatting utilities for FPV Copilot Sky
 */

/**
 * Format bitrate value for display
 * Converts kbps to Mbps when >= 1000 kbps (1 Mbps)
 *
 * @param {number} kbps - Bitrate in kbps
 * @returns {string} Formatted bitrate string (e.g., "2500 kbps" or "1.5 Mbps")
 */
export function formatBitrate(kbps) {
  if (!kbps && kbps !== 0) return '—'

  // Convert to Mbps if >= 1000 kbps (1 Mbps)
  if (kbps >= 1000) {
    const mbps = kbps / 1000
    // Show one decimal if needed, otherwise whole number
    return mbps % 1 === 0 ? `${mbps} Mbps` : `${mbps.toFixed(1)} Mbps`
  }

  return `${kbps} kbps`
}
