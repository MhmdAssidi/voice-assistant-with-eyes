// One stored frame in detail (owner: Student A, task A10).
// The full image with what the system found drawn on top of it:
//   orange boxes = text read by OCR (A5), blue boxes = objects found by YOLO (A6).
// Boxes are drawn in an SVG whose coordinates are the image's own pixels, so they
// stay in place at any screen size. Hovering a row in the tables highlights its box.

import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { ApiError, api, describeError } from '../api/client'
import { useNow } from '../hooks/useNow'
import { timeAgo } from '../lib/time'
import type { DetectedObject, FrameDetail as Frame, OcrBlock } from '../types'
import './Frames.css'

type BoxKey = `ocr-${number}` | `obj-${number}`

interface Loaded {
  id: number
  frame?: Frame
  error?: string
  notFound?: boolean
}

function percent(value: number): string {
  return `${Math.round(value * 100)}%`
}

interface BoxProps {
  bbox: number[]
  label: string
  kind: 'ocr' | 'obj'
  active: boolean
  imageWidth: number
}

function Box({ bbox, label, kind, active, imageWidth }: BoxProps) {
  const [x1, y1, x2, y2] = bbox
  const fontSize = Math.max(12, imageWidth / 45) // readable whatever the image size
  const labelY = y1 > fontSize + 4 ? y1 - 4 : y2 + fontSize + 2 // above the box, or below at the top edge
  return (
    <g className={`box box-${kind}${active ? ' box-active' : ''}`}>
      <rect x={x1} y={y1} width={x2 - x1} height={y2 - y1} />
      <text x={x1 + 2} y={labelY} fontSize={fontSize}>
        {label}
      </text>
    </g>
  )
}

export default function FrameDetail() {
  const { id } = useParams()
  const frameId = Number(id)
  const navigate = useNavigate()
  const location = useLocation()
  const now = useNow()
  // The answer for one frame id; while it belongs to another id, the page is loading
  const [result, setResult] = useState<Loaded>({ id: NaN })
  const [showOcr, setShowOcr] = useState(true)
  const [showObjects, setShowObjects] = useState(true)
  const [active, setActive] = useState<BoxKey | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .frame(frameId)
      .then((frame) => !cancelled && setResult({ id: frameId, frame }))
      .catch((e: unknown) => {
        if (cancelled) return
        if (e instanceof ApiError && e.status === 404) setResult({ id: frameId, notFound: true })
        else setResult({ id: frameId, error: describeError(e) })
      })
    return () => {
      cancelled = true
    }
  }, [frameId])

  const current = result.id === frameId ? result : { id: frameId }
  const { frame = null, error = '', notFound = false } = current

  // Back to where the user came from (Timeline, Search or History), else the Timeline
  const goBack = () => (location.key === 'default' ? navigate('/timeline') : navigate(-1))

  return (
    <section aria-labelledby="frame-title">
      <div className="page-head">
        <button type="button" className="link-button" onClick={goBack}>
          ← Back
        </button>
        <h2 id="frame-title">Frame {id}</h2>
        {frame && (
          <p className="muted">
            <time dateTime={frame.captured_at}>{new Date(frame.captured_at).toLocaleString()}</time> ·{' '}
            {timeAgo(frame.captured_at, now)}
          </p>
        )}
      </div>

      {notFound && (
        <div className="panel empty-state">
          <p>
            <strong>This frame does not exist anymore.</strong>
          </p>
          <p className="muted">
            Old frames are deleted automatically after a while (privacy). <Link to="/timeline">See the timeline</Link>
          </p>
        </div>
      )}
      {error && (
        <p className="error" role="alert">
          Could not load the frame: {error}
        </p>
      )}
      {!frame && !notFound && !error && <p className="muted">Loading…</p>}

      {frame && (
        <div className="detail-layout">
          <figure className="detail-figure">
            <div className="detail-image">
              <img src={frame.image_url} alt={`Frame ${frame.id} as captured by the phone camera`} />
              <svg
                viewBox={`0 0 ${frame.width} ${frame.height}`}
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                {showObjects &&
                  frame.objects.map((o, i) => (
                    <Box
                      key={`obj-${i}`}
                      bbox={o.bbox}
                      label={`${o.label} ${percent(o.confidence)}`}
                      kind="obj"
                      active={active === `obj-${i}`}
                      imageWidth={frame.width}
                    />
                  ))}
                {showOcr &&
                  frame.ocr_blocks.map((b, i) => (
                    <Box
                      key={`ocr-${i}`}
                      bbox={b.bbox}
                      label={b.text}
                      kind="ocr"
                      active={active === `ocr-${i}`}
                      imageWidth={frame.width}
                    />
                  ))}
              </svg>
            </div>
            <figcaption className="box-toggles">
              <label>
                <input type="checkbox" checked={showOcr} onChange={(e) => setShowOcr(e.target.checked)} />
                <span className="swatch swatch-ocr" /> Text boxes ({frame.ocr_blocks.length})
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={showObjects}
                  onChange={(e) => setShowObjects(e.target.checked)}
                />
                <span className="swatch swatch-obj" /> Object boxes ({frame.objects.length})
              </label>
              <a href={frame.image_url} target="_blank" rel="noreferrer">
                Open full image
              </a>
            </figcaption>
          </figure>

          <div className="detail-side">
            <div className="panel">
              <h3>Text read (OCR)</h3>
              {frame.ocr_blocks.length === 0 ? (
                <p className="muted">No text was read in this frame.</p>
              ) : (
                <OcrTable blocks={frame.ocr_blocks} onHover={setActive} />
              )}
            </div>

            <div className="panel">
              <h3>Objects</h3>
              {frame.objects.length === 0 ? (
                <p className="muted">No objects were detected.</p>
              ) : (
                <ObjectTable objects={frame.objects} onHover={setActive} />
              )}
            </div>

            <div className="panel">
              <h3>Image quality</h3>
              <dl className="facts">
                <dt>Size</dt>
                <dd>
                  {frame.width} × {frame.height} px
                </dd>
                <dt>Sharpness</dt>
                <dd>{frame.sharpness.toFixed(0)} (Laplacian variance; below 60 is blurry)</dd>
                <dt>Brightness</dt>
                <dd>{frame.brightness.toFixed(0)} / 255</dd>
                <dt>Enhanced</dt>
                <dd>{frame.enhanced ? 'yes: brightened before reading (dark scene)' : 'no'}</dd>
              </dl>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

type OnHover = (key: BoxKey | null) => void

function OcrTable({ blocks, onHover }: { blocks: OcrBlock[]; onHover: OnHover }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th scope="col">Text</th>
          <th scope="col">Confidence</th>
        </tr>
      </thead>
      <tbody>
        {blocks.map((b, i) => (
          <tr key={i} onMouseEnter={() => onHover(`ocr-${i}`)} onMouseLeave={() => onHover(null)}>
            <td dir="auto">{b.text}</td>
            <td>{percent(b.confidence)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function ObjectTable({ objects, onHover }: { objects: DetectedObject[]; onHover: OnHover }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          <th scope="col">Object</th>
          <th scope="col">Where</th>
          <th scope="col">Confidence</th>
        </tr>
      </thead>
      <tbody>
        {objects.map((o, i) => (
          <tr key={i} onMouseEnter={() => onHover(`obj-${i}`)} onMouseLeave={() => onHover(null)}>
            <td>{o.label}</td>
            <td>
              {o.position}
              {o.near && <strong> · near</strong>}
            </td>
            <td>{percent(o.confidence)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
