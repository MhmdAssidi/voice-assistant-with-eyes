// Live stream page (owner: Student A, task A13).
// Plays the phone's camera straight from MediaMTX (WHEP); the backend is not involved.
// Above the video: live stairs / closed-door warnings from the ingest worker (A11).

import { whepUrl } from '../api/client'
import WarningFeed from '../components/WarningFeed'
import WhepPlayer from '../components/WhepPlayer'

export default function Live() {
  return (
    <section className="panel" aria-labelledby="live-title">
      <h2 id="live-title">Live stream</h2>
      <WarningFeed />
      <WhepPlayer />
      <p className="hint">
        Source: <code>{whepUrl()}</code>. Video only: the phone keeps its microphone free
        for questions.
      </p>
    </section>
  )
}
