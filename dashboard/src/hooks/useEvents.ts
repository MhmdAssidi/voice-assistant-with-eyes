// Live events from the backend (owner: Student B, task B11).
// One WebSocket to /ws/events (forwarded to the API by vite.config.ts). If it drops
// (API restarted, Wi-Fi change), it reconnects by itself after 1, 2, 4... max 10 s.

import { useEffect, useRef, useState } from 'react'
import type { AppEvent } from '../types'

const MAX_RETRY_MS = 10_000

function eventsUrl(): string {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${window.location.host}/ws/events`
}

/** Calls onEvent for every event; returns true while the live connection is open. */
export function useEvents(onEvent: (event: AppEvent) => void): boolean {
  const [connected, setConnected] = useState(false)
  // Keep the latest callback without reconnecting each time the component re-renders.
  const handler = useRef(onEvent)
  useEffect(() => {
    handler.current = onEvent
  }, [onEvent])

  useEffect(() => {
    let socket: WebSocket | null = null
    let retryTimer: number | undefined
    let retryMs = 1000
    let stopped = false

    const connect = () => {
      socket = new WebSocket(eventsUrl())
      socket.onopen = () => {
        retryMs = 1000
        setConnected(true)
      }
      socket.onmessage = (message) => {
        try {
          handler.current(JSON.parse(message.data as string) as AppEvent)
        } catch {
          // ignore a malformed message rather than breaking the page
        }
      }
      socket.onclose = () => {
        setConnected(false)
        if (stopped) return
        retryTimer = window.setTimeout(connect, retryMs)
        retryMs = Math.min(retryMs * 2, MAX_RETRY_MS)
      }
    }

    connect()
    return () => {
      stopped = true
      window.clearTimeout(retryTimer)
      socket?.close()
    }
  }, [])

  return connected
}
