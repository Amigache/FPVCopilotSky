import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useWebSocket } from './WebSocketContext'
import { useToast } from './ToastContext'
import { API_MAVLINK, fetchWithTimeout } from '../services/api'

const ParamCacheContext = createContext(null)

export const useParamCache = () => {
  const context = useContext(ParamCacheContext)
  if (!context) {
    throw new Error('useParamCache must be used within ParamCacheProvider')
  }
  return context
}

export const ParamCacheProvider = ({ children }) => {
  const { t } = useTranslation()
  const { showToast } = useToast()
  const { messages } = useWebSocket()

  const [params, setParams] = useState({})
  const [isDownloading, setIsDownloading] = useState(false)
  const [status, setStatus] = useState({
    total: 0,
    loaded: 0,
    phase: '',
    progress: 0,
    partial: false,
    error: null,
  })

  const downloadPromiseRef = useRef(null)
  const startedThisConnectionRef = useRef(false)

  const clearCache = useCallback(() => {
    setParams({})
    setIsDownloading(false)
    setStatus({
      total: 0,
      loaded: 0,
      phase: '',
      progress: 0,
      partial: false,
      error: null,
    })
    downloadPromiseRef.current = null
    startedThisConnectionRef.current = false
  }, [])

  const mergeParams = useCallback((updates) => {
    if (!updates || typeof updates !== 'object') return
    setParams((prev) => ({ ...prev, ...updates }))
  }, [])

  const refreshParamsCache = useCallback(
    async ({ force = false, showCompletionToast = true, resetCacheBeforeLoad = false } = {}) => {
      if (downloadPromiseRef.current) {
        return downloadPromiseRef.current
      }

      if (!force && Object.keys(params).length > 0) {
        return { success: true, parameters: params, from_cache: true }
      }

      if (resetCacheBeforeLoad) {
        setParams({})
      }

      setIsDownloading(true)
      setStatus({
        total: 0,
        loaded: 0,
        phase: t('views.flightController.loadingPhaseRequesting'),
        progress: 0,
        partial: false,
        error: null,
      })

      const promise = (async () => {
        let pollTimer = null
        try {
          pollTimer = setInterval(async () => {
            try {
              const statusRes = await fetch(`${API_MAVLINK}/params/cache/status`)
              if (!statusRes.ok) return
              const live = await statusRes.json()
              if (live.expected > 0) {
                const loaded = Math.min(live.loaded, live.expected)
                const progress = Math.min(Math.round((loaded / live.expected) * 100), 99)
                setStatus((prev) => ({
                  ...prev,
                  total: live.expected,
                  loaded,
                  phase: t('views.flightController.loadingPhaseRequesting'),
                  progress,
                }))
              } else if (live.loaded > 0) {
                setStatus((prev) => ({
                  ...prev,
                  loaded: live.loaded,
                  phase: t('views.flightController.loadingPhaseRequesting'),
                }))
              }
            } catch (_) {
              // Ignore transient polling errors
            }
          }, 400)

          const response = await fetchWithTimeout(
            `${API_MAVLINK}/params/batch/get`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                params: [],
                include_all: true,
                force_refresh: force,
              }),
            },
            120000
          )

          const data = await response.json()
          if (!response.ok || !data.parameters) {
            const message =
              data?.detail || data?.error || t('views.flightController.paramsLoadError')
            setStatus((prev) => ({ ...prev, error: message }))
            return { success: false, error: message }
          }

          const loadedParams = { ...data.parameters }
          const loadedCount = Object.keys(loadedParams).length
          const expectedCount = data.meta?.cache_expected_count || loadedCount
          const partial = Boolean(data.meta?.cache_partial)

          setParams(loadedParams)
          setStatus({
            total: expectedCount,
            loaded: Math.min(loadedCount, expectedCount || loadedCount),
            phase: t('views.flightController.loadingPhaseFinalizing'),
            progress: 100,
            partial,
            error: null,
          })

          if (showCompletionToast) {
            if (partial) {
              showToast(
                `${t('views.flightController.paramsLoaded')} (${loadedCount}). ${t(
                  'views.flightController.paramsLoadError'
                )}: parcial`,
                'warning'
              )
            } else {
              showToast(`${t('views.flightController.paramsLoaded')} (${loadedCount})`, 'success')
            }
          }

          return { success: true, parameters: loadedParams, partial }
        } catch (error) {
          const message = error?.message || t('views.flightController.paramsLoadError')
          setStatus((prev) => ({ ...prev, error: message }))
          return { success: false, error: message }
        } finally {
          if (pollTimer) {
            clearInterval(pollTimer)
          }
          setIsDownloading(false)
          downloadPromiseRef.current = null
        }
      })()

      downloadPromiseRef.current = promise
      return promise
    },
    [params, showToast, t]
  )

  // Start background download once MAVLink is connected and telemetry is present.
  useEffect(() => {
    const connected = Boolean(messages?.mavlink_status?.connected)
    const hasTelemetryFrame = Boolean(messages?.telemetry)

    if (!connected) {
      clearCache()
      return
    }

    if (!hasTelemetryFrame) {
      return
    }

    if (startedThisConnectionRef.current) {
      return
    }

    startedThisConnectionRef.current = true
    refreshParamsCache({ force: true, showCompletionToast: true, resetCacheBeforeLoad: true })
  }, [messages, clearCache, refreshParamsCache])

  const value = {
    params,
    isDownloading,
    isLoaded: Object.keys(params).length > 0,
    status,
    refreshParamsCache,
    clearCache,
    mergeParams,
  }

  return <ParamCacheContext.Provider value={value}>{children}</ParamCacheContext.Provider>
}
