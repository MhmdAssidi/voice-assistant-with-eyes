// Shared API contract v1.0 (SHARED file).
// Mirrors backend/app/contracts.py field for field. Datetimes arrive as ISO-8601 strings.
// Change only through a `contract/...` pull request approved by both students.

export type Language = 'en' | 'fr' | 'ar'

export interface DetectedObject {
  label: string
  confidence: number
  bbox: number[] // [x1, y1, x2, y2]
  position: 'left' | 'center' | 'right'
  near: boolean
}

export interface OcrBlock {
  text: string
  confidence: number
  bbox: number[]
}

export interface FrameSummary {
  id: number
  captured_at: string
  thumb_url: string
  ocr_text: string
  object_labels: string[]
  enhanced: boolean
}

export interface FrameDetail extends FrameSummary {
  image_url: string
  width: number
  height: number
  sharpness: number
  brightness: number
  ocr_blocks: OcrBlock[]
  objects: DetectedObject[]
}

export interface SearchHit {
  frame: FrameSummary
  score: number
  matched_by: Array<'image' | 'text' | 'ocr' | 'time'>
}

export interface Evidence {
  frame_id: number
  captured_at: string
  thumb_url: string
  score: number
}

export interface AskResponse {
  id: number
  question: string
  language: Language
  answer: string
  confident: boolean
  evidence: Evidence[]
  timings_ms: Record<string, number> // keys: stt, search, vlm, total
}

export interface QaRecord extends AskResponse {
  asked_at: string
}

export interface SystemStatus {
  stream_connected: boolean
  ingest_running: boolean
  frames_seen: number
  frames_kept: number
  frame_count: number
  last_frame_at: string | null
  avg_process_ms: number
  last_question_at: string | null
}

export type EventType = 'frame_stored' | 'ingest_status' | 'question_answered' | 'warning'

export interface AppEvent {
  type: EventType
  ts: string
  data: Record<string, unknown>
}
