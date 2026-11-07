// Live hazard warnings under the video (owner: Student A, task A11).
// The ingest worker sends a `warning` event when CLIP recognises stairs or a closed
// door ahead; the phone speaks it (Student B), the dashboard lists it here.
// No warning does NOT mean the way is clear: the page never says so.

import { useCallback, useState } from 'react'
import { Link } from 'react-router-dom'
import { useEvents } from '../hooks/useEvents'
import { useNow } from '../hooks/useNow'
import { clockTime, timeAgo } from '../lib/time'
import type { AppEvent } from '../types'
import './WarningFeed.css'

const MAX_SHOWN = 6
const RECENT_MS = 10_000 // highlighted while this fresh

interface Warning {
  kind: string
  confidence: number
  frameId: number
  position: string
  ts: string
}

const KIND_TEXT: Record<string, string> = {
  stairs: 'Stairs ahead',
  closed_door: 'Closed door ahead',
}

function toWarning(event: AppEvent): Warning | null {
  const d = event.data
  if (event.type !== 'warning' || typeof d.kind !== 'string') return null
  return {
    kind: d.kind,
    confidence: Number(d.confidence ?? 0),
    frameId: Number(d.frame_id ?? 0),
    position: String(d.position ?? 'center'),
    ts: event.ts,
  }
}

export default function WarningFeed() {
  const [warnings, setWarnings] = useState<Warning[]>([])
  const now = useNow(1000)

  const onEvent = useCallback((event: AppEvent) => {
    const warning = toWarning(event)
    if (warning) setWarnings((list) => [warning, ...list].slice(0, MAX_SHOWN))
  }, [])
  const live = useEvents(onEvent)

  return (
    <section className="warning-feed" aria-labelledby="warnings-title">
      <h3 id="warnings-title">Warnings</h3>
      {/* role="log" + aria-live: a screen reader announces each new warning */}
      <ul role="log" aria-live="assertive" className="warning-list">
        {warnings.map((w, i) => {
          const recent = now - new Date(w.ts).getTime() < RECENT_MS
          return (
            <li key={`${w.ts}-${i}`} className={`warning-item${recent ? ' warning-recent' : ''}`}>
              <span className="warning-icon" aria-hidden="true">
                ⚠
              </span>
              <strong>{KIND_TEXT[w.kind] ?? w.kind}</strong>
              <span className="muted">
                {Math.round(w.confidence * 100)}% · {clockTime(w.ts)} ({timeAgo(w.ts, now)})
              </span>
              {w.frameId > 0 && <Link to={`/frames/${w.frameId}`}>frame {w.frameId}</Link>}
            </li>
          )
        })}
      </ul>
      {warnings.length === 0 && (
        <p className="muted">
          {live
            ? 'No warning since this page was opened. This is not a promise that the way is clear.'
            : 'Reconnecting to live updates…'}
        </p>
      )}
    </section>
  )
}
