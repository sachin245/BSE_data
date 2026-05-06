import { useEffect, useRef } from 'react'
import type { Announcement } from '../api'

interface FilingDetailProps {
  announcement: Announcement
  onClose: () => void
}

const formatDate = (iso: string | null): string => (iso ? iso.slice(0, 10) : '—')

export function FilingDetail({ announcement, onClose }: FilingDetailProps) {
  const closeRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    closeRef.current?.focus()
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const a = announcement
  const subjectDiffersFromHeadline = a.headline && a.headline !== a.subject

  return (
    <div
      className="detail-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="detail-title"
      onClick={onClose}
    >
      <aside className="detail-panel" onClick={(e) => e.stopPropagation()}>
        <header className="detail-header">
          <div>
            <h2 id="detail-title" className="detail-title">
              {a.companyName || a.scripCode}
            </h2>
            <p className="detail-meta">
              <span className="mono">{a.scripCode}</span>
              {a.segment ? <span> · {a.segment}</span> : null}
              {a.dtFiled ? <span> · Filed {formatDate(a.dtFiled)}</span> : null}
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="detail-close"
            aria-label="Close detail"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <section className="detail-section">
          <h3>Subject</h3>
          <p>{a.subject}</p>
        </section>

        {subjectDiffersFromHeadline ? (
          <section className="detail-section">
            <h3>Headline</h3>
            <p>{a.headline}</p>
          </section>
        ) : null}

        {a.scrapeTagHits.length > 0 ? (
          <section className="detail-section">
            <h3>Match Tags ({a.scrapeTagHits.length})</h3>
            <ul className="detail-tag-list">
              {a.scrapeTagHits.map((t) => (
                <li key={t.tagId} className="detail-tag">
                  <strong>{t.tagLabel}</strong>
                  {t.matchedText ? <span className="detail-tag__match"> — “{t.matchedText}”</span> : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {a.flagHits.length > 0 ? (
          <section className="detail-section">
            <h3>Flag Hits ({a.flagHits.length})</h3>
            <ul className="detail-flag-list">
              {a.flagHits.map((h) => (
                <li key={h.name} className="detail-flag">
                  <strong>{h.name}</strong>
                  <p className="detail-flag__snippet">{h.snippet}</p>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <footer className="detail-footer">
          {a.attachmentUrl ? (
            <a
              className="detail-action"
              href={a.attachmentUrl}
              target="_blank"
              rel="noopener noreferrer"
            >
              View PDF on BSE
            </a>
          ) : (
            <span className="detail-no-pdf">No attachment URL</span>
          )}
        </footer>
      </aside>
    </div>
  )
}
