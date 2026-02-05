/**
 * API Configuration
 * Centralized API URL configuration for connecting to FastAPI backend
 */

// Get the API base URL - always use port 8000 (FastAPI backend)
export const getApiBaseUrl = () => {
  const protocol = window.location.protocol
  const hostname = window.location.hostname
  return `${protocol}//${hostname}:8000`
}

// API endpoints
export const API_BASE = getApiBaseUrl()
export const API_MAVLINK = `${API_BASE}/api/mavlink`
export const API_MAVLINK_ROUTER = `${API_BASE}/api/mavlink-router`
export const API_SYSTEM = `${API_BASE}/api/system`

// Helper function for fetch with timeout
export const fetchWithTimeout = async (url, options = {}, timeout = 10000) => {
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
  get: (endpoint, timeout = 10000) => 
    fetchWithTimeout(`${API_BASE}${endpoint}`, {}, timeout),
  
  post: (endpoint, data, timeout = 10000) => 
    fetchWithTimeout(`${API_BASE}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    }, timeout),
  
  delete: (endpoint, timeout = 10000) => 
    fetchWithTimeout(`${API_BASE}${endpoint}`, {
      method: 'DELETE'
    }, timeout)
}

export default api
