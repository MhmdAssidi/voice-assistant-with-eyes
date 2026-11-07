// Past questions and answers (owner: Student B, task B11).
// Loads the history once, then new answers appear at the top instantly
// (question_answered events on the WebSocket), without reloading the page.

import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useEvents } from '../hooks/useEvents'
import type { AppEvent, QaRecord } from '../types'
import './History.css'

const LANGUAGE_NAMES: Record<string, string> = { en: 'English', fr: 'Français', ar: 'العربية' }

const TIMING_LABELS: Array<[string, string]> = [
  ['stt', 'speech-to-text'],
  ['search', 'search'],
  ['vlm', 'AI answer'],
  ['total', 'total'],
]

function seconds(ms: number | undefined): string {
  if (ms === undefined) return '–'
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
}

function sameRecord(a: QaRecord, b: QaRecord): boolean {
  // id 0 = not saved (database down): compare by time instead.
  return a.id !== 0 ? a.id === b.id : a.asked_at === b.asked_at
}

export default function History() {
  const [records, setRecords] = useState<QaRecord[]>([])
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    api
      .questions()
      .then((list) => {
        setRecords(list)
        setLoaded(true)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  const onEvent = useCallback((event: AppEvent) => {
    if (event.type !== 'question_answered') return
    const record = event.data as unknown as QaRecord
    setRecords((list) => [record, ...list.filter((r) => !sameRecord(r, record))])
  }, [])
  const live = useEvents(onEvent)

  return (
    <section aria-labelledby="history-title">
      <h2 id="history-title">Questions and answers</h2>
      <p className="history-note">
        {live ? 'New questions appear here as soon as they are answered.' : 'Reconnecting to live updates…'}
      </p>
      {error && <p className="error">Could not load the history: {error}</p>}
      {loaded && records.length === 0 && (
        <p className="placeholder">No questions yet. Ask one from the phone.</p>
      )}

      {records.map((r) => (
        <article key={`${r.id}-${r.asked_at}`} className="panel qa">
          <header className="qa-meta">
            <time dateTime={r.asked_at}>{new Date(r.asked_at).toLocaleString()}</time>
            <span className="badge">{LANGUAGE_NAMES[r.language] ?? r.language}</span>
            {/* text + symbol, not colour only */}
            <span className={`badge ${r.confident ? 'badge-ok' : 'badge-unsure'}`}>
              {r.confident ? '✓ confident' : '? not sure'}
            </span>
          </header>

          <p className="qa-question" dir="auto">
            <strong>Q:</strong> {r.question || <em>(no speech heard)</em>}
          </p>
          <p className="qa-answer" dir="auto">
            <strong>A:</strong> {r.answer}
          </p>

          {r.evidence.length > 0 && (
            <div className="qa-evidence" aria-label="Frames used for the answer">
              {r.evidence.map((e) => {
                const image = (
                  <img
                    src={e.thumb_url}
                    alt={e.frame_id === 0 ? 'Live camera view when the question was asked'
                      : `Frame ${e.frame_id}, score ${e.score.toFixed(2)}`}
                    loading="lazy"
                    onError={(ev) => {
                      ev.currentTarget.style.visibility = 'hidden' // file deleted (retention)
                    }}
                  />
                )
                // frame_id 0 = live snapshot taken at question time (not a stored frame)
                return e.frame_id === 0 ? (
                  <span key={`live-${e.thumb_url}`} className="qa-thumb">
                    {image}
                    <span>live view</span>
                  </span>
                ) : (
                  <Link key={e.frame_id} to={`/frames/${e.frame_id}`} className="qa-thumb">
                    {image}
                    <span>
                      #{e.frame_id} · {e.score.toFixed(2)}
                    </span>
                  </Link>
                )
              })}
            </div>
          )}

          <p className="qa-timings">
            {TIMING_LABELS.map(([key, label]) => (
              <span key={key}>
                {label}: <strong>{seconds(r.timings_ms[key])}</strong>
              </span>
            ))}
          </p>
        </article>
      ))}
    </section>
  )
}
