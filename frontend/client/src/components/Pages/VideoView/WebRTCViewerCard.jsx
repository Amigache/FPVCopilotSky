import { useState, useRef, useCallback, useEffect, useImperativeHandle, forwardRef } from 'react'
import { useTranslation } from 'react-i18next'
import api from '../../../services/api'

// Helper function to apply bandwidth constraint to SDP
function applyBandwidthConstraint(sdp, maxBitrateKbps) {
  if (!sdp || !maxBitrateKbps) return sdp
  // Add bandwidth constraint after m=video line
  return sdp.replace(/(m=video.*\r\n)/, `$1b=AS:${maxBitrateKbps}\r\n`)
}

const WebRTCViewerCard = forwardRef(({ onStatsUpdate }, ref) => {
  const { t } = useTranslation()
  const videoRef = useRef(null)
  const pcRef = useRef(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [connectionState, setConnectionState] = useState('disconnected')
  const statsIntervalRef = useRef(null)
  const prevBytesRef = useRef(0)
  const prevTimestampRef = useRef(0)
  const containerRef = useRef(null)
  const peerIdRef = useRef(null)

  // Function definitions must come before hooks that use them
  const stopStatsCollection = useCallback(() => {
    if (statsIntervalRef.current) {
      clearInterval(statsIntervalRef.current)
      statsIntervalRef.current = null
    }
  }, [])

  const startStatsCollection = useCallback(
    (pc, pId) => {
      if (statsIntervalRef.current) clearInterval(statsIntervalRef.current)

      statsIntervalRef.current = setInterval(async () => {
        try {
          const stats = await pc.getStats()
          let inboundVideo = null
          let candidatePair = null

          stats.forEach((report) => {
            if (report.type === 'inbound-rtp' && report.kind === 'video') {
              inboundVideo = report
            }
            if (report.type === 'candidate-pair' && report.state === 'succeeded') {
              candidatePair = report
            }
          })

          if (inboundVideo) {
            const now = performance.now()
            const bytes = inboundVideo.bytesReceived || 0
            const elapsed = (now - (prevTimestampRef.current || now)) / 1000

            const bitrate =
              elapsed > 0 ? Math.round(((bytes - prevBytesRef.current) * 8) / elapsed / 1000) : 0

            prevBytesRef.current = bytes
            prevTimestampRef.current = now

            const newStats = {
              resolution: inboundVideo.frameWidth
                ? `${inboundVideo.frameWidth}x${inboundVideo.frameHeight}`
                : '-',
              fps: inboundVideo.framesPerSecond || 0,
              bitrate: Math.max(0, bitrate),
              rtt: candidatePair ? Math.round((candidatePair.currentRoundTripTime || 0) * 1000) : 0,
              packetsLost: inboundVideo.packetsLost || 0,
              jitter: inboundVideo.jitter ? Math.round(inboundVideo.jitter * 1000) : 0,
            }

            if (onStatsUpdate) onStatsUpdate(newStats)

            // Report stats to server
            api
              .post('/api/webrtc/stats', {
                peer_id: pId,
                stats: {
                  rtt_ms: newStats.rtt,
                  bitrate_kbps: newStats.bitrate,
                  fps: newStats.fps,
                  packets_lost: newStats.packetsLost,
                  jitter_ms: newStats.jitter,
                },
              })
              .catch(() => {})
          }
        } catch {
          // Stats collection failed, ignore
        }
      }, 2000)
    },
    [onStatsUpdate]
  )

  const disconnectPeer = useCallback(() => {
    stopStatsCollection()
    if (pcRef.current) {
      pcRef.current.close()
      pcRef.current = null
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
    const currentPeerId = peerIdRef.current
    if (currentPeerId) {
      api.post('/api/webrtc/disconnect', { peer_id: currentPeerId }).catch(() => {})
    }
    setConnectionState('disconnected')
    peerIdRef.current = null
    if (onStatsUpdate) {
      onStatsUpdate({ resolution: '-', fps: 0, bitrate: 0, rtt: 0, packetsLost: 0, jitter: 0 })
    }
  }, [onStatsUpdate, stopStatsCollection])

  const connectWebRTC = useCallback(async () => {
    try {
      setConnectionState('connecting')

      // 1. Create session on server
      const sessionRes = await api.post('/api/webrtc/session', {})
      const sessionData = await sessionRes.json()
      if (!sessionRes.ok || !sessionData.success) {
        setConnectionState('failed')
        return
      }

      const newPeerId = sessionData.peer_id
      peerIdRef.current = newPeerId
      const config = sessionData.config

      // 2. Get 4G optimized config
      const optimRes = await api.get('/api/webrtc/4g-config')
      const optimConfig = optimRes.ok ? await optimRes.json() : {}

      // 3. Create RTCPeerConnection with 4G optimizations
      const pc = new RTCPeerConnection(config)
      pcRef.current = pc

      // Add transceiver for receiving video only
      pc.addTransceiver('video', { direction: 'recvonly' })

      // Handle incoming tracks
      pc.ontrack = (event) => {
        if (videoRef.current && event.streams[0]) {
          videoRef.current.srcObject = event.streams[0]
        }
      }

      // Monitor ICE connection state
      pc.oniceconnectionstatechange = () => {
        const state = pc.iceConnectionState
        if (state === 'connected' || state === 'completed') {
          setConnectionState('connected')
          api.post('/api/webrtc/connected', { peer_id: newPeerId }).catch(() => {})
          startStatsCollection(pc, newPeerId)
        } else if (state === 'failed' || state === 'disconnected') {
          setConnectionState('disconnected')
          stopStatsCollection()
        }
      }

      // Send ICE candidates to server
      pc.onicecandidate = (event) => {
        if (event.candidate) {
          api
            .post('/api/webrtc/ice-candidate', {
              peer_id: newPeerId,
              candidate: {
                candidate: event.candidate.candidate,
                sdpMid: event.candidate.sdpMid,
                sdpMLineIndex: event.candidate.sdpMLineIndex,
              },
            })
            .catch(() => {})
        }
      }

      // 4. Create offer with 4G constraints
      const offerOptions = optimConfig.sdp || {
        offerToReceiveVideo: true,
        offerToReceiveAudio: false,
      }
      const offer = await pc.createOffer(offerOptions)

      // Apply bandwidth constraints for 4G
      if (optimConfig.video?.maxBitrate) {
        offer.sdp = applyBandwidthConstraint(
          offer.sdp,
          Math.floor(optimConfig.video.maxBitrate / 1000)
        )
      }

      await pc.setLocalDescription(offer)

      // 5. Send offer to server and get SDP answer from aiortc
      const offerRes = await api.post('/api/webrtc/offer', {
        peer_id: newPeerId,
        sdp: offer.sdp,
        type: 'offer',
      })
      const offerData = await offerRes.json()

      if (!offerRes.ok || !offerData.success || !offerData.sdp) {
        console.error('WebRTC: server did not return SDP answer', offerData)
        setConnectionState('failed')
        return
      }

      // 6. Set remote description (server's answer) to complete SDP exchange
      await pc.setRemoteDescription(
        new RTCSessionDescription({ type: 'answer', sdp: offerData.sdp })
      )

      setConnectionState('connecting')
    } catch (error) {
      console.error('WebRTC connect error:', error)
      setConnectionState('failed')
    }
  }, [startStatsCollection, stopStatsCollection])

  // Expose connect/disconnect to parent
  useImperativeHandle(
    ref,
    () => ({
      connect: connectWebRTC,
      disconnect: disconnectPeer,
      connectionState,
    }),
    [connectWebRTC, disconnectPeer, connectionState]
  )

  // Auto-connect when component mounts (stream already started)
  useEffect(() => {
    connectWebRTC() // eslint-disable-line react-hooks/set-state-in-effect
    return () => {
      disconnectPeer()
      if (statsIntervalRef.current) clearInterval(statsIntervalRef.current)
    }
  }, [connectWebRTC, disconnectPeer])

  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return

    if (!document.fullscreenElement) {
      containerRef.current
        .requestFullscreen()
        .then(() => setIsFullscreen(true))
        .catch(() => {})
    } else {
      document
        .exitFullscreen()
        .then(() => setIsFullscreen(false))
        .catch(() => {})
    }
  }, [])

  // Listen for fullscreen change
  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement)
    document.addEventListener('fullscreenchange', handler)
    return () => document.removeEventListener('fullscreenchange', handler)
  }, [])

  return (
    <div
      className={`card webrtc-viewer-card ${isFullscreen ? 'fullscreen' : ''}`}
      data-testid="webrtc-viewer-card"
      ref={containerRef}
    >
      <div className="webrtc-viewer-header">
        <h2>{t('views.video.webrtcViewer')}</h2>
      </div>

      {/* Video Player */}
      <div className="webrtc-video-container">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="webrtc-video"
          data-testid="webrtc-video"
        />
        {connectionState !== 'connected' && (
          <div className="webrtc-video-overlay">
            {connectionState === 'connecting' && (
              <div className="webrtc-connecting">
                <div className="spinner-small" />
                <span>{t('views.video.webrtcConnecting')}</span>
              </div>
            )}
            {connectionState === 'failed' && (
              <span className="webrtc-error">{t('views.video.webrtcFailed')}</span>
            )}
          </div>
        )}
      </div>

      {/* Fullscreen button — full width at bottom */}
      <button
        className="btn btn-fullscreen-bottom"
        onClick={toggleFullscreen}
        title={t('views.video.webrtcFullscreen')}
      >
        {isFullscreen ? '⛶ ' : '⛶ '}
        {t('views.video.webrtcFullscreen')}
      </button>
    </div>
  )
})

export default WebRTCViewerCard
