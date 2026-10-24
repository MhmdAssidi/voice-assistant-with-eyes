// One stored frame in detail (owner: Student A, task A10).

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { FrameDetail as Frame } from '../types'

export default function FrameDetail() {
  const { id } = useParams()
  const [frame, setFrame] = useState<Frame | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .frame(Number(id))
      .then(setFrame)
      .catch((e: Error) => setError(e.message))
  }, [id])

  return (
    <section className="panel" aria-labelledby="frame-title">
      <p>
        <Link to="/timeline">← Back to timeline</Link>
      </p>
      <h2 id="frame-title">Frame {id}</h2>
      {error && <p className="error">{error}</p>}
      {frame && (
        <dl>
          <dt>Captured</dt>
          <dd>{new Date(frame.captured_at).toLocaleString()}</dd>
          <dt>Text read (OCR)</dt>
          <dd>{frame.ocr_text || '(none)'}</dd>
          <dt>Objects</dt>
          <dd>{frame.object_labels.join(', ') || '(none)'}</dd>
          <dt>Sharpness / brightness</dt>
          <dd>
            {frame.sharpness} / {frame.brightness}
          </dd>
        </dl>
      )}
      <p className="placeholder">S0 placeholder: the full image and object boxes come in A10.</p>
    </section>
  )
}
