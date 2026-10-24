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
