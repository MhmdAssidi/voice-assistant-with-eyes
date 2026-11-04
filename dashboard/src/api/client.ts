// REST helpers (owner: Student A; Student B adds functions through a PR).
// Relative URLs work because vite.config.ts forwards /api to the backend.

import type { FrameDetail, FrameSummary, QaRecord, SearchHit, SystemStatus } from '../types'

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText} for ${url}`)
  }
  return (await response.json()) as T
}

export const api = {
  health: () => getJson<{ status: string }>('/api/health'),
  frames: (limit = 50) => getJson<FrameSummary[]>(`/api/frames?limit=${limit}`),
  frame: (id: number) => getJson<FrameDetail>(`/api/frames/${id}`),
  search: (q: string, limit = 10) =>
    getJson<SearchHit[]>(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  questions: (limit = 50) => getJson<QaRecord[]>(`/api/questions?limit=${limit}`),
  status: () => getJson<SystemStatus>('/api/status'),
}

/** WHEP URL of the live stream: VITE_WHEP_URL from dashboard/.env, else MediaMTX on the
 *  same host as the page (works for http://localhost:5173 and http://LAN_IP:5173). */
export function whepUrl(): string {
  const fromEnv = import.meta.env.VITE_WHEP_URL as string | undefined
  return fromEnv || `http://${window.location.hostname}:8889/live/whep`
}
