// Minimal WHEP player: plays the phone's camera from MediaMTX over WebRTC
// (owner: Student A, task A13).
//
// WHEP in four steps:
//   1. create an RTCPeerConnection that only RECEIVES video,
//   2. POST our SDP offer to http://HOST:8889/live/whep (Content-Type application/sdp),
//   3. MediaMTX replies 201 with its SDP answer (and a Location URL for this session),
//   4. the video track arrives in `ontrack` and is attached to a muted autoplay <video>.
// WebRTC sends frames as soon as they are decoded (no HLS-style segments), so the delay
// stays well under a second on the same Wi-Fi.

import { useCallback, useEffect, useRef, useState } from 'react'
import { whepUrl } from '../api/client'

type PlayerState = 'connecting' | 'playing' | 'offline' | 'error'

const RETRY_MS = 5000 // try again automatically while nobody is publishing
const ICE_GATHER_TIMEOUT_MS = 2000

/** Wait until the browser has listed its network addresses (no trickle ICE needed on a LAN). */
function waitForIceGathering(pc: RTCPeerConnection): Promise<void> {
  if (pc.iceGatheringState === 'complete') return Promise.resolve()
  return new Promise((resolve) => {
    const done = () => {
      pc.removeEventListener('icegatheringstatechange', check)
      clearTimeout(timer)
      resolve()
    }
    const check = () => {
      if (pc.iceGatheringState === 'complete') done()
    }
    const timer = setTimeout(done, ICE_GATHER_TIMEOUT_MS)
    pc.addEventListener('icegatheringstatechange', check)
  })
}

export default function WhepPlayer({ url = whepUrl() }: { url?: string }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [state, setState] = useState<PlayerState>('connecting')
  const [message, setMessage] = useState('')
  const [attempt, setAttempt] = useState(0) // bump to reconnect

  const reconnect = useCallback(() => setAttempt((n) => n + 1), [])

  useEffect(() => {
    let cancelled = false
    let retryTimer: ReturnType<typeof setTimeout> | undefined
    let sessionUrl: string | null = null
    const pc = new RTCPeerConnection() // no STUN/TURN: phone and laptop share the network

    const goOffline = (text: string) => {
      if (cancelled) return
      setState('offline')
      setMessage(text)
      retryTimer = setTimeout(reconnect, RETRY_MS)
    }

    pc.addTransceiver('video', { direction: 'recvonly' })
    pc.ontrack = (event) => {
      const video = videoRef.current
      if (!video) return
      video.srcObject = event.streams[0] ?? new MediaStream([event.track])
      video.play().catch(() => {}) // muted autoplay is allowed; ignore a cancelled play()
    }
    pc.onconnectionstatechange = () => {
      if (cancelled) return
      if (pc.connectionState === 'connected') {
        setState('playing')
        setMessage('')
      } else if (pc.connectionState === 'failed' || pc.connectionState === 'disconnected') {
        goOffline('The stream stopped. Reconnecting…')
      }
    }

    async function start() {
      setState('connecting')
      setMessage('')
      try {
        await pc.setLocalDescription(await pc.createOffer())
        await waitForIceGathering(pc)
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/sdp' },
          body: pc.localDescription?.sdp,
        })
        if (cancelled) return
        if (response.status === 404) {
          goOffline('No camera is streaming yet. Start the stream on the phone.')
          return
        }
        if (!response.ok) throw new Error(`MediaMTX answered ${response.status}`)
        const location = response.headers.get('Location')
        sessionUrl = location ? new URL(location, url).toString() : null
        await pc.setRemoteDescription({ type: 'answer', sdp: await response.text() })
      } catch (error) {
        if (cancelled) return
        // fetch() throws a TypeError when MediaMTX itself is unreachable
        if (error instanceof TypeError) {
          goOffline('Cannot reach the streaming server on port 8889. Is docker compose up?')
        } else {
          setState('error')
          setMessage(error instanceof Error ? error.message : String(error))
        }
      }
    }

    start()

    return () => {
      cancelled = true
      clearTimeout(retryTimer)
      pc.close()
      // Tell MediaMTX to free this viewer's session right away (best effort)
      if (sessionUrl) fetch(sessionUrl, { method: 'DELETE' }).catch(() => {})
    }
  }, [url, attempt, reconnect])

  const label: Record<PlayerState, string> = {
    connecting: 'Connecting…',
    playing: 'Live',
    offline: 'Offline',
    error: 'Error',
  }

  return (
    <div className="whep">
      <div className="video-box">
        <video
          ref={videoRef}
          className={state === 'playing' ? '' : 'hidden'}
          muted
          autoPlay
          playsInline
          aria-label="Live camera from the phone"
        />
        {state !== 'playing' && <div className="video-overlay">{label[state]}</div>}
      </div>
      <div className="player-controls">
        <span role="status" aria-live="polite">
          <span className={state === 'playing' ? 'ok' : 'off'}>{label[state]}</span>
          {message && <span className="muted"> · {message}</span>}
        </span>
        <button type="button" onClick={reconnect}>
          Reconnect
        </button>
      </div>
    </div>
  )
}
