// Search stored frames by meaning (owner: Student A, task A10).

import { type FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { SearchHit } from '../types'

export default function Search() {
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<SearchHit[]>([])
  const [error, setError] = useState('')

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (!query.trim()) return
    setError('')
    api
      .search(query)
      .then(setHits)
      .catch((e: Error) => setError(e.message))
  }

  return (
    <section aria-labelledby="search-title">
      <h2 id="search-title">Search</h2>
      <form onSubmit={onSubmit} className="panel" role="search">
        <label htmlFor="q">Find frames by meaning (English, French or Arabic): </label>
        <input
          id="q"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="exit sign / sortie / مخرج"
        />{' '}
        <button type="submit">Search</button>
      </form>
      {error && <p className="error">{error}</p>}
      <div className="grid">
        {hits.map((h) => (
          <Link key={h.frame.id} to={`/frames/${h.frame.id}`} className="card">
            <strong>Frame {h.frame.id}</strong> · score {h.score.toFixed(2)}
            <div>{h.frame.ocr_text || '(no text)'}</div>
            <small>matched by: {h.matched_by.join(', ')}</small>
          </Link>
        ))}
      </div>
    </section>
  )
}
