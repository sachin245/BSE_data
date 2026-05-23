// Typed API client for the BSE Scraper backend.
// Endpoint shapes mirror backend/server/main.py.

export interface FlagHit {
  name: string
  snippet: string
}

export interface ScrapeTagHit {
  tagId: string
  tagLabel: string
  matchedText: string | null
}

export interface Announcement {
  id: string
  scripCode: string
  companyName: string | null
  segment: string | null
  subject: string
  headline: string
  category: string | null
  dtFiled: string | null
  attachmentUrl: string | null
  attachmentPath: string | null
  processedAt: string | null
  flagHits: FlagHit[]
  scrapeTagHits: ScrapeTagHit[]
}

export interface LogEntry {
  ts: string
  msg: string
  level: 'info' | 'warn' | 'err'
}

export interface ScraperStatus {
  running: boolean
  phase: string
  startedAt: string | null
  finishedAt: string | null
  rangeFrom: string | null
  rangeTo: string | null
  universe: boolean
  watchlistOnly: boolean
  dryRun: boolean
  totalPages: number
  pagesDone: number
  recordsScanned: number
  matched: number
  newRecords: number
  pdfsOk: number
  pdfsFailed: number
  http429s: number
  http503s: number
  progress: number
  log: LogEntry[]
}

export interface ProcessorStatus {
  running: boolean
  phase: string
  startedAt: string | null
  finishedAt: string | null
  mode: string | null
  totalRecords: number
  processed: number
  flagHits: number
  pdfErrors: number
  progress: number
  log: LogEntry[]
}

export interface RunStatus {
  activeStep: string | null
  scraper: ScraperStatus
  processor: ProcessorStatus
}

export interface RunHistoryEntry {
  id: number
  step: string
  started_at: string
  finished_at: string | null
  range_from: string | null
  range_to: string | null
  pages_fetched: number
  records_scanned: number
  matched: number
  new_records: number
  pdfs_ok: number
  pdfs_failed: number
  pdfs_processed: number
  flag_hit_total: number
  http_429s: number
  http_503s: number
  elapsed_sec: number
  status: string | null
}

export interface FilterTag {
  id: string
  label: string
  pattern: string
  isActive: boolean
}

export interface ProcessorFlag {
  name: string
  pattern: string
  active: boolean
  caseInsensitive?: boolean
}

export interface AppConfig {
  scraper: Record<string, unknown>
  filter: {
    tags: FilterTag[]
    tagsEnabled: boolean
    watchlist: string[]
    watchlistOnly: boolean
  }
  processor: {
    flags: ProcessorFlag[]
  }
}

export interface ConfigResponse {
  config: AppConfig
  mtime: string | null
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = 'ApiError'
  }
}

async function apiErrorMessage(res: Response, path: string): Promise<string> {
  const fallback = `${res.status} ${res.statusText} - ${path}`
  const contentType = res.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) return fallback

  try {
    const body = (await res.json()) as { error?: unknown; detail?: unknown }
    const message = body.error ?? body.detail
    return typeof message === 'string' && message.trim() ? message : fallback
  } catch {
    return fallback
  }
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: { Accept: 'application/json' } })
  if (!res.ok) {
    throw new ApiError(res.status, await apiErrorMessage(res, path))
  }
  return (await res.json()) as T
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  if (!res.ok) {
    throw new ApiError(res.status, await apiErrorMessage(res, path))
  }
  return (await res.json()) as T
}

export const api = {
  fetchAnnouncements: () => getJson<Announcement[]>('/api/announcements'),
  fetchStatus: () => getJson<RunStatus>('/api/status'),
  fetchHistory: () => getJson<RunHistoryEntry[]>('/api/history'),
  fetchConfig: () => getJson<ConfigResponse>('/api/config'),
  saveConfig: (partial: Partial<AppConfig>) =>
    postJson<ConfigResponse>('/api/config', partial),
  startScraper: (payload: Record<string, unknown>) =>
    postJson<ScraperStatus>('/api/scraper/start', payload),
  startProcessor: (payload: Record<string, unknown>) =>
    postJson<ProcessorStatus>('/api/processor/start', payload),
  startQuickRun: (payload: Record<string, unknown>) =>
    postJson<ScraperStatus>('/api/quickrun/start', payload),
  stopRun: () => postJson<RunStatus>('/api/run/stop', {}),
  fetchLogs: (source: string = 'backend', limit: number = 100) =>
    getJson<{ logs: string[] }>(`/api/logs?source=${source}&limit=${limit}`),
}
