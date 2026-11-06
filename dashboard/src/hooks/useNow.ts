// The current time, refreshed every few seconds, so "12 s ago" labels stay right
// (owner: Student A, task A10).

import { useEffect, useState } from 'react'

export function useNow(intervalMs = 5000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(timer)
  }, [intervalMs])
  return now
}
