// Timeline of stored frames (owner: Student A, task A10).
// S0 version: lists the stub frames from /api/frames to prove the connection works.

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { FrameSummary } from '../types'

export default function Timeline() {
  const [frames, setFrames] = useState<FrameSummary[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    api.frames().then(setFrames).catch((e: Error) => setError(e.message))
  }, [])

  return (
    <section aria-labelledby="timeline-title">
      <h2 id="timeline-title">Timeline</h2>
      <p className="placeholder">S0 placeholder: thumbnails and live updates come in A10.</p>
      {error && <p className="error">{error}</p>}
      <div className="grid">
        {frames.map((f) => (
          <Link key={f.id} to={`/frames/${f.id}`} className="card">
            <strong>Frame {f.id}</strong>
            <div>{f.ocr_text || '(no text)'}</div>
            <small>
              {new Date(f.captured_at).toLocaleTimeString()} · {f.object_labels.join(', ')}
            </small>
          </Link>
        ))}
      </div>
    </section>
  )
}
