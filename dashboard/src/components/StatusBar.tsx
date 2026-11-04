// Live system status shown on every page (owner: Student B, S0 + B11).
// Loads /api/status once, then updates from WebSocket events instead of polling.
// The ingest worker sends ingest_status every 2 s; after 5 s of silence the stream
// is shown as not connected (the worker may have stopped without saying so).

import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { useEvents } from '../hooks/useEvents'
import type { AppEvent, SystemStatus } from '../types'

const STALE_AFTER_MS = 5000

function timeAgo(iso: string | null, now: number): string {
  if (!iso) return 'never'
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  if (seconds < 60) return `${seconds} s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  return new Date(iso).toLocaleTimeString()
}

export default function StatusBar() {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [offline, setOffline] = useState(false)
  const [lastIngestAt, setLastIngestAt] = useState(0) // our clock, ms
  const [now, setNow] = useState(() => Date.now())

  // First picture of the system; also reloaded every time the live connection comes back.
  const load = useCallback(() => {
    api
      .status()
      .then((s) => {
        setStatus(s)
        setOffline(false)
        if (s.stream_connected || s.ingest_running) setLastIngestAt(Date.now())
      })
      .catch(() => setOffline(true))
  }, [])

  const onEvent = useCallback((event: AppEvent) => {
    const data = event.data
    setStatus((s) => {
      if (!s) return s
      switch (event.type) {
        case 'ingest_status':
          return {
            ...s,
            stream_connected: Boolean(data.stream_connected),
            ingest_running: Boolean(data.ingest_running),
            frames_seen: Number(data.frames_seen ?? s.frames_seen),
            frames_kept: Number(data.frames_kept ?? s.frames_kept),
            avg_process_ms: Number(data.avg_process_ms ?? s.avg_process_ms),
          }
        case 'frame_stored':
          return { ...s, frame_count: s.frame_count + 1, last_frame_at: String(data.captured_at) }
        case 'question_answered':
          return { ...s, last_question_at: String(data.asked_at) }
        default:
          return s
      }
    })
    if (event.type === 'ingest_status') setLastIngestAt(Date.now())
  }, [])

  const live = useEvents(onEvent)

  useEffect(load, [load])
  useEffect(() => {
    if (live) load()
  }, [live, load])
  // Re-render every second so "x s ago" and the 5-second staleness stay current.
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  if (offline && !live) {
    return (
      <div className="status-bar" role="status">
        <span className="off">Backend offline</span>
        <span>Start it with: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000</span>
      </div>
    )
  }
  if (!status) return <div className="status-bar">Loading status…</div>

  const fresh = now - lastIngestAt <= STALE_AFTER_MS
  const streamOn = fresh && status.stream_connected
  const ingestOn = fresh && status.ingest_running

  // Words carry the meaning (connected / not connected), colour only repeats it.
  return (
    <div className="status-bar" role="status">
      <span>
        Stream: <span className={streamOn ? 'ok' : 'off'}>{streamOn ? 'connected' : 'not connected'}</span>
      </span>
      <span>
        Ingest: <span className={ingestOn ? 'ok' : 'off'}>{ingestOn ? 'running' : 'stopped'}</span>
      </span>
      <span>Frames stored: {status.frame_count}</span>
      <span>
        Kept {status.frames_kept} of {status.frames_seen} seen
        {status.avg_process_ms > 0 && ` · ${status.avg_process_ms} ms/frame`}
      </span>
      <span>Last question: {timeAgo(status.last_question_at, now)}</span>
      <span>
        Live updates: <span className={live ? 'ok' : 'off'}>{live ? 'on' : 'reconnecting…'}</span>
      </span>
    </div>
  )
}
