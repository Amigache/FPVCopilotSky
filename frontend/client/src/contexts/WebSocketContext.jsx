import { createContext, useContext, useEffect, useState, useRef, useCallback } from 'react'

const WebSocketContext = createContext(null)

export const useWebSocket = () => {
  const context = useContext(WebSocketContext)
  if (!context) {
    throw new Error('useWebSocket must be used within WebSocketProvider')
  }
  return context
}

// Get WebSocket URL - always connect to backend port 8000
const getWebSocketUrl = () => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const hostname = window.location.hostname
  // Always use port 8000 for WebSocket (FastAPI backend)
  return `${protocol}//${hostname}:8000/ws`
}

export const WebSocketProvider = ({ children }) => {
  const [isConnected, setIsConnected] = useState(false)
  const [messages, setMessages] = useState({})
  const wsRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)
  const isConnectingRef = useRef(false)
  const isMountedRef = useRef(true)

  const connect = useCallback(() => {
    // Prevent multiple simultaneous connection attempts
    if (isConnectingRef.current || wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }
    
    isConnectingRef.current = true

    const wsUrl = getWebSocketUrl()
    console.log('🔌 Connecting to WebSocket:', wsUrl)
    
    try {
      const ws = new WebSocket(wsUrl)

      ws.onopen = () => {
        if (!isMountedRef.current) {
          ws.close()
          return
        }
        console.log('🟢 WebSocket connected')
        isConnectingRef.current = false
        setIsConnected(true)
      }

      ws.onmessage = (event) => {
        if (!isMountedRef.current) return
        try {
          // Ignore ping/pong messages
          if (event.data === 'pong') return
          
          const message = JSON.parse(event.data)
          
          // Update messages state with the new data
          setMessages(prev => ({
            ...prev,
            [message.type]: message.data
          }))
        } catch (error) {
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
    } catch (error) {
      isConnectingRef.current = false
    }
  }, [])

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

  const value = {
    isConnected,
    messages,
    send: (data) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data))
      }
    }
  }

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  )
}
