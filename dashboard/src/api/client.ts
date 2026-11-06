// REST helpers (owner: Student A; Student B adds functions through a PR).
// Relative URLs work because vite.config.ts forwards /api to the backend.

import type { FrameDetail, FrameSummary, QaRecord, SearchHit, SystemStatus } from '../types'

/** An HTTP error that keeps the status code (404 = frame deleted, 503 = database down). */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText} for ${url}`)
  }
  return (await response.json()) as T
}

/** "?limit=50&before_id=12", leaving out empty values. */
function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export interface FrameListOptions {
  limit?: number // 1..200, default 50
  beforeId?: number // next page: frames older than this id
  since?: string // ISO-8601
  until?: string
}

export interface SearchOptions {
  limit?: number // 1..50, default 10
  since?: string
  until?: string
}

export const api = {
  health: () => getJson<{ status: string }>('/api/health'),
  frames: (options: FrameListOptions = {}) =>
    getJson<FrameSummary[]>(
      `/api/frames${query({
        limit: options.limit,
        before_id: options.beforeId,
        since: options.since,
        until: options.until,
      })}`,
    ),
  frame: (id: number) => getJson<FrameDetail>(`/api/frames/${id}`),
  search: (q: string, options: SearchOptions = {}) =>
    getJson<SearchHit[]>(
      `/api/search${query({ q, limit: options.limit, since: options.since, until: options.until })}`,
    ),
  questions: (limit = 50) => getJson<QaRecord[]>(`/api/questions?limit=${limit}`),
  status: () => getJson<SystemStatus>('/api/status'),
}

/** A message a person can act on, for any error thrown by the api functions. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 503) return 'The database is not reachable. Is Docker (Postgres) running?'
    if (error.status === 502 || error.status === 504) return 'The backend is not running (port 8000).'
    return error.message
  }
  if (error instanceof TypeError) return 'The backend is not reachable. Is it running on port 8000?'
  return error instanceof Error ? error.message : String(error)
}

/** WHEP URL of the live stream: VITE_WHEP_URL from dashboard/.env, else MediaMTX on the
 *  same host as the page (works for http://localhost:5173 and http://LAN_IP:5173). */
export function whepUrl(): string {
  const fromEnv = import.meta.env.VITE_WHEP_URL as string | undefined
  return fromEnv || `http://${window.location.hostname}:8889/live/whep`
}
