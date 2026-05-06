// Frontend log forwarder. POSTs to /api/logs (handled in backend/server/main.py).
// Throttled and resilient: dropped entries are tracked rather than retried,
// and a failed POST is silenced after the first warning to avoid loops.

type LogLevel = 'INFO' | 'WARN' | 'ERROR'

interface QueuedEntry {
  level: LogLevel
  message: string
}

const FLUSH_INTERVAL_MS = 1000
const MAX_QUEUE = 100

const queue: QueuedEntry[] = []
let dropped = 0
let networkFailed = false
let flushTimer: ReturnType<typeof setTimeout> | null = null

const flush = async (): Promise<void> => {
  flushTimer = null
  if (queue.length === 0) return

  const batch = queue.splice(0, queue.length)
  if (dropped > 0) {
    batch.unshift({ level: 'WARN', message: `dropped ${dropped} log entries (queue overflow)` })
    dropped = 0
  }

  for (const entry of batch) {
    try {
      const res = await fetch('/api/logs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(entry),
        keepalive: true,
      })
      if (!res.ok && !networkFailed) {
        networkFailed = true
        console.warn(`[logger] /api/logs returned ${res.status}; further failures suppressed`)
      }
    } catch (err) {
      if (!networkFailed) {
        networkFailed = true
        console.warn('[logger] /api/logs unreachable; further failures suppressed', err)
      }
    }
  }
}

const scheduleFlush = (): void => {
  if (flushTimer !== null) return
  flushTimer = setTimeout(() => {
    void flush()
  }, FLUSH_INTERVAL_MS)
}

const enqueue = (level: LogLevel, message: string): void => {
  if (queue.length >= MAX_QUEUE) {
    dropped += 1
    return
  }
  queue.push({ level, message })
  scheduleFlush()
}

if (typeof window !== 'undefined') {
  window.addEventListener('beforeunload', () => {
    if (queue.length === 0) return
    try {
      const blob = new Blob([JSON.stringify(queue)], { type: 'application/json' })
      navigator.sendBeacon('/api/logs', blob)
    } catch {
      // ignore — page is unloading
    }
  })
}

export const logInfo = (message: string): void => {
  console.log(`[INFO] ${message}`)
  enqueue('INFO', message)
}

export const logWarn = (message: string): void => {
  console.warn(`[WARN] ${message}`)
  enqueue('WARN', message)
}

export const logError = (message: string | Error): void => {
  const errMsg = message instanceof Error ? message.stack || message.message : message
  console.error(`[ERROR] ${errMsg}`)
  enqueue('ERROR', errMsg)
}
