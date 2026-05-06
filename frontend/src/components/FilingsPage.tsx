import { useEffect, useMemo, useState } from 'react'
import { api, ApiError, type Announcement } from '../api'
import { logError, logInfo } from '../logger'
import { FilingsFilters, type FilterState } from './FilingsFilters'
import { FilingsTable } from './FilingsTable'
import { FilingDetail } from './FilingDetail'

export function FilingsPage() {
  const [announcements, setAnnouncements] = useState<Announcement[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filters, setFilters] = useState<FilterState>({
    query: '',
    segment: 'All',
    matchedOnly: false,
  })
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const fetchData = async (): Promise<void> => {
    try {
      const data = await api.fetchAnnouncements()
      setAnnouncements(data)
      logInfo(`Loaded ${data.length} announcement(s)`)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e as Error).message
      setError(msg)
      logError(`Failed to fetch announcements: ${msg}`)
    }
  }

  const retry = (): void => {
    setError(null)
    setAnnouncements(null)
    void fetchData()
  }

  useEffect(() => {
    // Initial fetch on mount. The set-state-in-effect rule flags this as a
    // cascading-render risk, but for a one-shot mount fetch with no external
    // subscription, this is the documented pattern.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchData()
  }, [])

  const filtered = useMemo<Announcement[]>(() => {
    if (!announcements) return []
    const q = filters.query.trim().toLowerCase()
    return announcements.filter((a) => {
      if (filters.segment !== 'All') {
        if ((a.segment ?? '').toUpperCase() !== filters.segment.toUpperCase()) return false
      }
      if (filters.matchedOnly && a.scrapeTagHits.length === 0) return false
      if (q) {
        const company = (a.companyName ?? '').toLowerCase()
        const subject = a.subject.toLowerCase()
        const scrip = a.scripCode.toLowerCase()
        if (!company.includes(q) && !subject.includes(q) && !scrip.includes(q)) {
          return false
        }
      }
      return true
    })
  }, [announcements, filters])

  const selected = useMemo(
    () => (selectedId ? filtered.find((a) => a.id === selectedId) ?? null : null),
    [filtered, selectedId],
  )

  const handleFilterChange = (next: Partial<FilterState>) => {
    setFilters((prev) => ({ ...prev, ...next }))
  }

  return (
    <div className="filings-page">
      <FilingsFilters filters={filters} onChange={handleFilterChange} />

      {announcements === null && error === null ? (
        <div className="state-block loading-state" role="status" aria-live="polite">
          Loading filings…
        </div>
      ) : null}

      {error ? (
        <div className="state-block error-state" role="alert">
          <p>Failed to load filings: {error}</p>
          <button type="button" className="state-action" onClick={retry}>
            Retry
          </button>
        </div>
      ) : null}

      {announcements && !error ? (
        announcements.length === 0 ? (
          <div className="state-block empty-state">
            No filings in the database yet. Run the scraper to populate data.
          </div>
        ) : (
          <>
            <p className="filings-count">
              Showing {filtered.length} of {announcements.length} filings
            </p>
            {filtered.length === 0 ? (
              <div className="state-block empty-state">
                No filings match the current filters.
              </div>
            ) : (
              <FilingsTable
                rows={filtered}
                selectedId={selectedId}
                onRowClick={setSelectedId}
              />
            )}
          </>
        )
      ) : null}

      {selected ? (
        <FilingDetail announcement={selected} onClose={() => setSelectedId(null)} />
      ) : null}
    </div>
  )
}
