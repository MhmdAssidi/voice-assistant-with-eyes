// Timeline of stored frames, newest first (owner: Student A, task A10).
// - first page from GET /api/frames, older pages with before_id when scrolling down
// - new frames appear at the top instantly (frame_stored events on the WebSocket)
// - frames are grouped by minute, so a walk reads like a story

import { useCallback, useEffect, useRef, useState } from 'react'
import { api, describeError } from '../api/client'
import FrameCard from '../components/FrameCard'
import { useEvents } from '../hooks/useEvents'
import { useNow } from '../hooks/useNow'
import { minuteLabel } from '../lib/time'
import type { AppEvent, FrameSummary } from '../types'
import './Frames.css'

const PAGE_SIZE = 48
const NEW_HIGHLIGHT_MS = 8000

interface Group {
  label: string
  frames: FrameSummary[]
}

/** Consecutive frames captured in the same minute share one heading. */
function groupByMinute(frames: FrameSummary[], now: number): Group[] {
  const groups: Group[] = []
  for (const frame of frames) {
    const label = minuteLabel(frame.captured_at, now)
    const last = groups.at(-1)
    if (last && last.label === label) last.frames.push(frame)
    else groups.push({ label, frames: [frame] })
  }
  return groups
}

function isFrameSummary(data: Record<string, unknown>): boolean {
  return typeof data.id === 'number' && typeof data.captured_at === 'string'
}

export default function Timeline() {
  const [frames, setFrames] = useState<FrameSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [hasOlder, setHasOlder] = useState(true)
  const [error, setError] = useState('')
  const [newIds, setNewIds] = useState<Set<number>>(() => new Set())
  const now = useNow()
  const sentinel = useRef<HTMLDivElement>(null)
  const busy = useRef(false) // one page request at a time

  const loadPage = useCallback((beforeId?: number) => {
    if (busy.current) return
    busy.current = true
    setLoading(true)
    api
      .frames({ limit: PAGE_SIZE, beforeId })
      .then((page) => {
        setFrames((list) => {
          const known = new Set(list.map((f) => f.id))
          return [...list, ...page.filter((f) => !known.has(f.id))]
        })
        setHasOlder(page.length === PAGE_SIZE)
        setError('')
      })
      .catch((e: unknown) => setError(describeError(e)))
      .finally(() => {
        busy.current = false
        setLoading(false)
      })
  }, [])

  const loadOlder = useCallback(() => {
    if (!hasOlder || frames.length === 0) return
    loadPage(frames[frames.length - 1].id)
  }, [frames, hasOlder, loadPage])

  // First page
  useEffect(() => loadPage(), [loadPage])

  // Infinite scroll: load the next page when the bottom of the list becomes visible
  useEffect(() => {
    const element = sentinel.current
    if (!element || !hasOlder) return
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) loadOlder()
    }, { rootMargin: '400px' })
    observer.observe(element)
    return () => observer.disconnect()
  }, [hasOlder, loadOlder])

  // Live: a frame stored by the ingest worker goes straight to the top
  const onEvent = useCallback((event: AppEvent) => {
    if (event.type !== 'frame_stored' || !isFrameSummary(event.data)) return
    const frame = event.data as unknown as FrameSummary
    setFrames((list) => (list.some((f) => f.id === frame.id) ? list : [frame, ...list]))
    setNewIds((ids) => new Set(ids).add(frame.id))
    window.setTimeout(() => {
      setNewIds((ids) => {
        const next = new Set(ids)
        next.delete(frame.id)
        return next
      })
    }, NEW_HIGHLIGHT_MS)
  }, [])
  const live = useEvents(onEvent)

  const groups = groupByMinute(frames, now)

  return (
    <section aria-labelledby="timeline-title">
      <div className="page-head">
        <h2 id="timeline-title">Timeline</h2>
        <p className="muted">
          {live ? 'New frames appear at the top as soon as they are stored.' : 'Reconnecting to live updates…'}
        </p>
      </div>

      {error && (
        <p className="error" role="alert">
          Could not load frames: {error}
        </p>
      )}
      {!loading && !error && frames.length === 0 && (
        <div className="panel empty-state">
          <p>
            <strong>No frames stored yet.</strong>
          </p>
          <p className="muted">
            Start streaming from the phone and run the ingest worker:{' '}
            <code>python -m app.ingest.worker</code>
          </p>
        </div>
      )}

      {groups.map((group, index) => (
        <section key={`${group.label}-${index}`} className="minute-group" aria-label={`Frames at ${group.label}`}>
          <h3 className="minute-label">
            {group.label}
            <span className="muted"> · {group.frames.length} {group.frames.length === 1 ? 'frame' : 'frames'}</span>
          </h3>
          <div className="frame-grid">
            {group.frames.map((frame) => (
              <FrameCard key={frame.id} frame={frame} now={now} isNew={newIds.has(frame.id)} />
            ))}
          </div>
        </section>
      ))}

      <div ref={sentinel} className="load-more">
        {loading && <p className="muted">Loading frames…</p>}
        {!loading && hasOlder && frames.length > 0 && (
          <button type="button" onClick={loadOlder}>
            Load older frames
          </button>
        )}
        {!hasOlder && frames.length > 0 && <p className="muted">That's all: {frames.length} frames.</p>}
      </div>
    </section>
  )
}
