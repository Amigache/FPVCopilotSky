import {
  createContext,
  useContext,
  useEffect,
  useState,
  useRef,
  useCallback,
  useMemo,
  useSyncExternalStore,
} from 'react'
import { getAuthToken } from '../services/api'

// Connection-level context: changes only on connect/disconnect, so consumers of
// this context do not re-render on every telemetry frame.
const ConnectionContext = createContext(null)
// Message store: per-type subscriptions so a component only re-renders when the
// message type it actually uses changes.
const MessageStoreContext = createContext(null)

export const useWebSocket = () => {
  const context = useContext(ConnectionContext)
  if (!context) {
    throw new Error('useWebSocket must be used within WebSocketProvider')
  }
  return context
}

// Alias clarifying intent; same object as useWebSocket().
export const useWsConnection = useWebSocket

/**
 * Subscribe to a single WebSocket message type.
 *
 * Returns the latest payload for `type` (or undefined), and only re-renders the
 * calling component when that specific type changes.
 */
export const useWsMessage = (type) => {
  const store = useContext(MessageStoreContext)
  if (!store) {
    throw new Error('useWsMessage must be used within WebSocketProvider')
  }
  const subscribe = useCallback((callback) => store.subscribe(type, callback), [store, type])
  const getSnapshot = useCallback(() => store.get(type), [store, type])
  return useSyncExternalStore(subscribe, getSnapshot, () => undefined)
}

// Get WebSocket URL
// - In production (served by nginx): use same host (nginx proxies /ws to backend)
// - In development (Vite dev server): connect to backend port 8000 directly
const getWebSocketUrl = () => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const hostname = window.location.hostname

  // In development (localhost:5173), use Vite's proxy or connect directly to backend
  if (import.meta.env.DEV) {
    // Vite proxy handles /ws, but for WebSocket we need to connect directly in some cases
    // Check if running on dev port 5173
    const port = window.location.port
    if (port === '5173' || port === '3000') {
      // Development mode - connect directly to backend
      return `${protocol}//${hostname}:8000/ws`
    }
  }

  // Production mode or same origin - use relative path (nginx will proxy)
  return `${protocol}//${hostname}${window.location.port ? ':' + window.location.port : ''}/ws`
}

export const createMessageStore = () => {
  const data = new Map()
  const listeners = new Map()

  return {
    get: (type) => data.get(type),
    set: (type, value) => {
      if (Object.is(data.get(type), value)) return
      data.set(type, value)
      const subscriberSet = listeners.get(type)
      if (subscriberSet) {
        subscriberSet.forEach((callback) => callback())
      }
    },
    subscribe: (type, callback) => {
      let subscriberSet = listeners.get(type)
      if (!subscriberSet) {
        subscriberSet = new Set()
        listeners.set(type, subscriberSet)
      }
      subscriberSet.add(callback)
      return () => {
        subscriberSet.delete(callback)
        if (subscriberSet.size === 0) {
          listeners.delete(type)
        }
      }
    },
  }
}

export const WebSocketProvider = ({ children }) => {
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)
  const isConnectingRef = useRef(false)
  const isMountedRef = useRef(true)
  const storeRef = useRef(null)
  if (!storeRef.current) {
    storeRef.current = createMessageStore()
  }
  const store = storeRef.current

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data))
    }
  }, [])

  const connect = useCallback(() => {
    // Prevent multiple simultaneous connection attempts
    if (isConnectingRef.current || wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    isConnectingRef.current = true

    const baseUrl = getWebSocketUrl()
    const token = getAuthToken()
    const wsUrl = token
      ? `${baseUrl}${baseUrl.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`
      : baseUrl

    try {
      const ws = new WebSocket(wsUrl)

      ws.onopen = () => {
        if (!isMountedRef.current) {
          ws.close()
          return
        }

        isConnectingRef.current = false
        setIsConnected(true)
      }

      ws.onmessage = (event) => {
        if (!isMountedRef.current) return
        try {
          // Ignore ping/pong messages
          if (event.data === 'pong') return

          const message = JSON.parse(event.data)

          // Update only the subscribers of this message type.
          store.set(message.type, message.data)
        } catch (_error) {
          // Silently ignore parse errors
        }
      }

      ws.onerror = () => {
        isConnectingRef.current = false
      }

      ws.onclose = () => {
        isConnectingRef.current = false
        wsRef.current = null

        if (!isMountedRef.current) return

        setIsConnected(false)

        // Attempt to reconnect after 3 seconds
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current)
        }
        reconnectTimeoutRef.current = setTimeout(() => {
          if (isMountedRef.current) {
            connect()
          }
        }, 3000)
      }

      wsRef.current = ws
    } catch (_error) {
      isConnectingRef.current = false
    }
  }, [store])

  useEffect(() => {
    isMountedRef.current = true
    connect()

    // Cleanup on unmount
    return () => {
      isMountedRef.current = false
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  // Keep connection alive with ping
  useEffect(() => {
    if (!isConnected) return

    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send('ping')
      }
    }, 30000)

    return () => clearInterval(pingInterval)
  }, [isConnected])

  const connectionValue = useMemo(() => ({ isConnected, send }), [isConnected, send])

  return (
    <MessageStoreContext.Provider value={store}>
      <ConnectionContext.Provider value={connectionValue}>{children}</ConnectionContext.Provider>
    </MessageStoreContext.Provider>
  )
}
