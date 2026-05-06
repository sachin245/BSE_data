import type { Announcement } from '../api'

interface FilingsTableProps {
  rows: Announcement[]
  selectedId: string | null
  onRowClick: (id: string) => void
}

const formatDate = (iso: string | null): string => (iso ? iso.slice(0, 10) : '—')

const truncate = (text: string, max = 80): string =>
  text.length > max ? text.slice(0, max - 1) + '…' : text

export function FilingsTable({ rows, selectedId, onRowClick }: FilingsTableProps) {
  return (
    <div className="filings-table-wrap">
      <table className="filings-table" aria-rowcount={rows.length}>
        <thead>
          <tr>
            <th scope="col">Filed</th>
            <th scope="col">Scrip</th>
            <th scope="col">Segment</th>
            <th scope="col">Company</th>
            <th scope="col">Subject</th>
            <th scope="col">Match Tags</th>
            <th scope="col">Flag Hits</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const matchTags = r.scrapeTagHits.map((h) => h.tagLabel).join(', ')
            const flagNames = r.flagHits.map((h) => h.name).join(', ')
            const isSelected = r.id === selectedId
            return (
              <tr
                key={r.id}
                className={isSelected ? 'filings-row filings-row--selected' : 'filings-row'}
                tabIndex={0}
                onClick={() => onRowClick(r.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onRowClick(r.id)
                  }
                }}
                aria-selected={isSelected}
              >
                <td>{formatDate(r.dtFiled)}</td>
                <td className="mono">{r.scripCode}</td>
                <td>{r.segment ?? ''}</td>
                <td>{r.companyName ?? ''}</td>
                <td title={r.subject}>{truncate(r.subject)}</td>
                <td className="filings-row__tags" title={matchTags}>{matchTags}</td>
                <td className="filings-row__flags" title={flagNames}>{flagNames}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
