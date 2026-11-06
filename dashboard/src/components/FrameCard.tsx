// One stored frame as a clickable card: thumbnail, time, text read, objects
// (owner: Student A, task A10). Used by the Timeline and Search pages.

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { clockTime, timeAgo } from '../lib/time'
import type { FrameSummary } from '../types'

const MAX_LABELS = 4

interface Props {
  frame: FrameSummary
  now: number
  isNew?: boolean // just arrived live: highlighted for a few seconds
  children?: ReactNode // extra lines, e.g. the search score
}

export default function FrameCard({ frame, now, isNew = false, children }: Props) {
  const text = frame.ocr_text.split(/\s+/).join(' ').trim()
  const labels = frame.object_labels.slice(0, MAX_LABELS)
  const hidden = frame.object_labels.length - labels.length

  return (
    <Link to={`/frames/${frame.id}`} className={`frame-card${isNew ? ' frame-card-new' : ''}`}>
      <div className="frame-thumb">
        <img
          src={frame.thumb_url}
          alt={text ? `Frame ${frame.id}: ${text}` : `Frame ${frame.id}`}
          loading="lazy"
          onError={(event) => {
            event.currentTarget.classList.add('missing') // file deleted: keep the card
          }}
        />
        {frame.enhanced && <span className="tag tag-enhanced">enhanced</span>}
        {isNew && <span className="tag tag-new">new</span>}
      </div>
      <div className="frame-body">
        <div className="frame-time">
          <time dateTime={frame.captured_at}>{clockTime(frame.captured_at)}</time>
          <span>{timeAgo(frame.captured_at, now)}</span>
        </div>
        <p className={`frame-text${text ? '' : ' empty'}`} dir="auto">
          {text || 'no text read'}
        </p>
        {labels.length > 0 && (
          <ul className="chips" aria-label="Objects seen">
            {labels.map((label) => (
              <li key={label} className="chip">
                {label}
              </li>
            ))}
            {hidden > 0 && <li className="chip chip-more">+{hidden}</li>}
          </ul>
        )}
        {children}
      </div>
    </Link>
  )
}
