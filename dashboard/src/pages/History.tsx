// Past questions and answers (owner: Student B, task B11).

import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { QaRecord } from '../types'

export default function History() {
  const [records, setRecords] = useState<QaRecord[]>([])
  const [error, setError] = useState('')

  useEffect(() => {
    api.questions().then(setRecords).catch((e: Error) => setError(e.message))
  }, [])

  return (
    <section aria-labelledby="history-title">
      <h2 id="history-title">Questions and answers</h2>
      <p className="placeholder">S0 placeholder: live updates and evidence thumbnails come in B11.</p>
      {error && <p className="error">{error}</p>}
      {records.map((r) => (
        <article key={r.id} className="panel">
          <small>
            {new Date(r.asked_at).toLocaleString()} · {r.language.toUpperCase()} ·{' '}
            {r.confident ? 'confident' : 'not sure'}
          </small>
          <p>
            <strong>Q:</strong> {r.question}
          </p>
          <p>
            <strong>A:</strong> {r.answer}
          </p>
        </article>
      ))}
    </section>
  )
}
