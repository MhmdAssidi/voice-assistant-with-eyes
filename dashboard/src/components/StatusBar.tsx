// Live system status shown on every page (owner: Student B).
// S0 version polls /api/status every 3 s; B11 switches it to WebSocket events.

import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { SystemStatus } from '../types'

export default function StatusBar() {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [offline, setOffline] = useState(false)

  useEffect(() => {
    const load = () =>
      api
        .status()
        .then((s) => {
          setStatus(s)
          setOffline(false)
        })
        .catch(() => setOffline(true))
    load()
    const timer = setInterval(load, 3000)
    return () => clearInterval(timer)
  }, [])

  if (offline) {
    return (
      <div className="status-bar" role="status">
        <span className="off">Backend offline</span>
        <span>Start it with: uvicorn app.main:app --reload --port 8000</span>
      </div>
    )
  }
  if (!status) return <div className="status-bar">Loading status…</div>

  return (
    <div className="status-bar" role="status" aria-live="polite">
      <span>
        Stream:{' '}
        <span className={status.stream_connected ? 'ok' : 'off'}>
          {status.stream_connected ? 'connected' : 'not connected'}
        </span>
      </span>
      <span>
        Ingest:{' '}
        <span className={status.ingest_running ? 'ok' : 'off'}>
          {status.ingest_running ? 'running' : 'stopped'}
        </span>
      </span>
      <span>Frames stored: {status.frame_count}</span>
      <span>
        Kept {status.frames_kept} of {status.frames_seen} seen
      </span>
    </div>
  )
}
