// Time formatting for the frame pages (owner: Student A, task A10).

/** "18:06:15" in the viewer's local time. */
export function clockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

/** "18:06", or "Nov 5, 18:06" when it is not today: the Timeline group headings. */
export function minuteLabel(iso: string, now = Date.now()): string {
  const date = new Date(iso)
  const time = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  if (date.toDateString() === new Date(now).toDateString()) return time
  return `${date.toLocaleDateString([], { month: 'short', day: 'numeric' })}, ${time}`
}

/** "12 s ago", "4 min ago", "2 h ago", else the date. */
export function timeAgo(iso: string, now = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  if (seconds < 60) return `${seconds} s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)} h ago`
  return new Date(iso).toLocaleDateString()
}
