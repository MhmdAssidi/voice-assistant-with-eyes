// Search stored frames by meaning, in English, French or Arabic (owner: Student A, task A10).
// Uses the same ranking as the assistant (GET /api/search, task A8). The question and
// the time range live in the URL (?q=...&range=...), so Back and shared links keep them.

import { type FormEvent, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, describeError } from '../api/client'
import FrameCard from '../components/FrameCard'
import { useNow } from '../hooks/useNow'
import type { SearchHit } from '../types'
import './Frames.css'

// Student B's CONFIDENCE_THRESHOLD (backend config): below it the assistant says "I'm not sure"
const CONFIDENCE_THRESHOLD = 0.25
const RESULT_LIMIT = 12

const RANGES = [
  { value: 'all', label: 'Any time', seconds: 0 },
  { value: '10m', label: 'Last 10 minutes (like the assistant)', seconds: 600 },
  { value: '1h', label: 'Last hour', seconds: 3600 },
  { value: '24h', label: 'Last 24 hours', seconds: 86_400 },
] as const

const EXAMPLES = ['exit sign', 'sortie', 'لافتة مخرج', 'stairs', 'a chair and a tv']

const MATCH_WORDS: Record<SearchHit['matched_by'][number], string> = {
  image: 'picture',
  text: 'caption',
  ocr: 'words read',
  time: 'time window',
}

interface Result {
  key: string // which question + range this answer belongs to
  hits?: SearchHit[]
  error?: string
  tookMs?: number
}

function ScoreBar({ score }: { score: number }) {
  const confident = score >= CONFIDENCE_THRESHOLD
  return (
    <div className="score">
      <div className="score-line">
        <span>
          Score <strong>{score.toFixed(2)}</strong>
        </span>
        <span className={confident ? 'ok' : 'off'}>{confident ? '✓ strong match' : '? weak match'}</span>
      </div>
      <div
        className="score-bar"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={score}
        aria-label="Match score"
      >
        <div className={`score-fill${confident ? '' : ' weak'}`} style={{ width: `${score * 100}%` }} />
        <div className="score-threshold" style={{ left: `${CONFIDENCE_THRESHOLD * 100}%` }} />
      </div>
    </div>
  )
}

export default function Search() {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const range = params.get('range') ?? 'all'
  const requestKey = `${range}|${q}`
  const [draft, setDraft] = useState(q)
  const [draftFor, setDraftFor] = useState(q)
  const [result, setResult] = useState<Result>({ key: '' })
  const now = useNow()

  // Keep the input in step with the URL (Back button, example chips)
  if (draftFor !== q) {
    setDraftFor(q)
    setDraft(q)
  }

  // Run the search whenever the question or the range in the URL changes
  useEffect(() => {
    if (!q.trim()) return
    let cancelled = false
    const seconds = RANGES.find((r) => r.value === range)?.seconds ?? 0
    const since = seconds ? new Date(Date.now() - seconds * 1000).toISOString() : undefined
    const started = performance.now()
    api
      .search(q, { limit: RESULT_LIMIT, since })
      .then((hits) => {
        if (!cancelled) {
          setResult({ key: requestKey, hits, tookMs: Math.round(performance.now() - started) })
        }
      })
      .catch((e: unknown) => !cancelled && setResult({ key: requestKey, error: describeError(e) }))
    return () => {
      cancelled = true
    }
  }, [q, range, requestKey])

  const searched = q.trim() !== ''
  const loading = searched && result.key !== requestKey
  const shown = searched && !loading ? result : { key: '' }
  const hits = shown.hits ?? (shown.error || !searched || loading ? null : [])
  const error = shown.error ?? ''
  const tookMs = shown.tookMs ?? 0

  const run = (question: string, newRange = range) => {
    const next: Record<string, string> = { q: question.trim() }
    if (newRange !== 'all') next.range = newRange
    setParams(next)
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (draft.trim()) run(draft)
  }

  return (
    <section aria-labelledby="search-title">
      <div className="page-head">
        <h2 id="search-title">Search</h2>
        <p className="muted">
          Find frames by meaning in English, French or Arabic: by the picture, its caption and the words
          read on signs.
        </p>
      </div>

      <form onSubmit={onSubmit} className="panel search-form" role="search">
        <label htmlFor="q" className="visually-hidden">
          Question
        </label>
        <input
          id="q"
          type="search"
          dir="auto"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="exit sign / sortie / مخرج"
        />
        <label htmlFor="range" className="visually-hidden">
          Time range
        </label>
        <select id="range" value={range} onChange={(e) => q && run(q, e.target.value)}>
          {RANGES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
        <button type="submit" disabled={!draft.trim() || loading}>
          {loading ? 'Searching…' : 'Search'}
        </button>
        <div className="examples">
          <span className="muted">Try:</span>
          {EXAMPLES.map((example) => (
            <button key={example} type="button" className="chip chip-button" dir="auto" onClick={() => run(example)}>
              {example}
            </button>
          ))}
        </div>
      </form>

      {error && (
        <p className="error" role="alert">
          Search failed: {error}
        </p>
      )}

      {hits !== null && !error && (
        <p className="muted" aria-live="polite">
          {hits.length === 0
            ? `No frames match “${q}”${range !== 'all' ? ' in this time range' : ''}.`
            : `${hits.length} ${hits.length === 1 ? 'frame' : 'frames'} for “${q}”, best first (${tookMs} ms). ` +
              `Below ${CONFIDENCE_THRESHOLD.toFixed(2)} the assistant would answer “I'm not sure”.`}
        </p>
      )}

      {hits && hits.length > 0 && (
        <div className="frame-grid">
          {hits.map((hit, rank) => (
            <FrameCard key={hit.frame.id} frame={hit.frame} now={now}>
              <p className="rank">#{rank + 1}</p>
              <ScoreBar score={hit.score} />
              {hit.matched_by.length > 0 && (
                <ul className="chips" aria-label="Matched by">
                  {hit.matched_by.map((m) => (
                    <li key={m} className={`chip match-${m}`}>
                      {MATCH_WORDS[m]}
                    </li>
                  ))}
                </ul>
              )}
            </FrameCard>
          ))}
        </div>
      )}
    </section>
  )
}
