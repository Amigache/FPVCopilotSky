/**
 * API Configuration
 * Centralized API URL configuration for connecting to FastAPI backend
 */

// Get the API base URL
// - In production (served by nginx): use relative paths (nginx proxies to backend)
// - In development (Vite dev server): use Vite's proxy configuration
export const getApiBaseUrl = () => {
  // In development mode (Vite dev server on port 5173)
  // Use empty string to leverage Vite's proxy configuration
  if (import.meta.env.DEV) {
    return ''
  }
  
  // In production (served by nginx)
  // Use relative paths - nginx will proxy /api/* to backend
  return ''
}

// API endpoints
export const API_BASE = getApiBaseUrl()
export const API_MAVLINK = `${API_BASE}/api/mavlink`
export const API_MAVLINK_ROUTER = `${API_BASE}/api/mavlink-router`
export const API_SYSTEM = `${API_BASE}/api/system`

// Helper function for fetch with timeout
// Default timeout is 30s to accommodate VPN/remote access latency
export const fetchWithTimeout = async (url, options = {}, timeout = 30000) => {
  const controller = new AbortController()
  const id = setTimeout(() => controller.abort(), timeout)
  
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal
    })
    clearTimeout(id)
    return response
  } catch (error) {
    clearTimeout(id)
    if (error.name === 'AbortError') {
      throw new Error('Request timeout')
    }
    throw error
  }
}

// Convenience methods for API calls
export const api = {
  get: (endpoint, timeout = 30000) => 
    fetchWithTimeout(`${API_BASE}${endpoint}`, {}, timeout),
  
  post: (endpoint, data, timeout = 30000) => 
    fetchWithTimeout(`${API_BASE}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }, timeout),
  
  delete: (endpoint, timeout = 30000) => 
    fetchWithTimeout(`${API_BASE}${endpoint}`, {
      method: 'DELETE'
    }, timeout),

  // VPN methods
  getVPNPeers: async () => {
    const response = await fetchWithTimeout(`${API_BASE}/api/vpn/peers`)
    if (!response.ok) {
      throw new Error(`Failed to fetch VPN peers: ${response.statusText}`)
    }
    return await response.json()
  },

  getVPNPreferences: async () => {
    const response = await fetchWithTimeout(`${API_BASE}/api/vpn/preferences`)
    if (!response.ok) {
      throw new Error(`Failed to fetch VPN preferences: ${response.statusText}`)
    }
    return await response.json()
  },

  saveVPNPreferences: async (preferences) => {
    const response = await fetchWithTimeout(`${API_BASE}/api/vpn/preferences`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(preferences)
    })
    if (!response.ok) {
      throw new Error(`Failed to save VPN preferences: ${response.statusText}`)
    }
    return await response.json()
  },

  // System restart methods
  restartBackend: async () => {
    const response = await fetchWithTimeout(`${API_BASE}/api/system/restart/backend`, {
      method: 'POST'
    }, 5000)
    if (!response.ok) {
      throw new Error(`Failed to restart backend: ${response.statusText}`)
    }
    return await response.json()
  },

  restartFrontend: async () => {
    const response = await fetchWithTimeout(`${API_BASE}/api/system/restart/frontend`, {
      method: 'POST'
    }, 5000)
    if (!response.ok) {
      throw new Error(`Failed to restart frontend: ${response.statusText}`)
    }
    return await response.json()
  },

  // System logs methods
  getBackendLogs: async (lines = 100) => {
    const response = await fetchWithTimeout(`${API_BASE}/api/system/logs/backend?lines=${lines}`)
    if (!response.ok) {
      throw new Error(`Failed to fetch backend logs: ${response.statusText}`)
    }
    return await response.json()
  },

  getFrontendLogs: async (lines = 100) => {
    const response = await fetchWithTimeout(`${API_BASE}/api/system/logs/frontend?lines=${lines}`)
    if (!response.ok) {
      throw new Error(`Failed to fetch frontend logs: ${response.statusText}`)
    }
    return await response.json()
  }
}

export default api
